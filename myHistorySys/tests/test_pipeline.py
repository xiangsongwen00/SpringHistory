"""Fixtures are explicitly synthetic, never history evidence. Integration uses private DB."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import unittest.mock
import uuid
from fastapi.testclient import TestClient
from historysys.api import app,escape_like
from historysys.db import connect,migrate
from historysys.importer import import_jsonl,validate
from import_folder import already_current
import import_folder

def fixture(book_id='TEST_SYNTHETIC'):
    body='合成测试五年内不加税赋。\n字面%_\\查询。'
    return {'schema_version':1,'book_id':book_id,'book_title':'SYNTHETIC TEST ONLY',
            'chapter_id':book_id+':0','chapter_index':0,'chapter_title':'合成测试，不是史料',
            'source_file':'synthetic-fixture','source_sha256':'0'*64,'decoder':'synthetic-test-v1',
            'verification_status':'decoded_unverified','text':body,
            'paragraphs':[{'ordinal':i,'text':t} for i,t in enumerate(body.splitlines())],
            'metadata':{'synthetic':True}}

class ValidationTests(unittest.TestCase):
    def test_validate(self):
        validate(fixture())
    def test_metadata_cannot_contain_body(self):
        r=fixture();r['verification_status']='metadata_only'
        with self.assertRaises(ValueError): validate(r)
    def test_paragraph_coverage(self):
        r=fixture();r['paragraphs']=r['paragraphs'][:1]
        with self.assertRaises(ValueError): validate(r)
    def test_like_escaping(self):
        self.assertEqual(escape_like('%_\\'),r'\%\_\\')
    def test_id_validation(self):
        r=fixture();r['chapter_id']='wrong'
        with self.assertRaises(ValueError): validate(r)
    def test_blank_source_title_preserved(self):
        r=fixture();r.update(chapter_title='',text=None,paragraphs=[],verification_status='metadata_only')
        self.assertEqual(validate(r)['chapter_title'],'')
    def test_bulk_indexes_restored_on_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'fixture.jsonl').write_text('{}\n',encoding='utf-8')
            with unittest.mock.patch('sys.argv',['import_folder.py',tmp,'--bulk-index-build']), \
                 unittest.mock.patch('launch_service.ensure_database'), \
                 unittest.mock.patch('import_folder.connect'), \
                 unittest.mock.patch('import_folder.already_current',return_value=False), \
                 unittest.mock.patch('import_folder.import_jsonl',side_effect=KeyboardInterrupt), \
                 unittest.mock.patch('import_folder.rebuild_indexes') as repair:
                with self.assertRaises(KeyboardInterrupt):import_folder.main()
                repair.assert_called_once_with()

@unittest.skipUnless(os.environ.get('HISTORY_TEST_DB')=='1','Explicit isolated DB opt-in required')
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=os.environ.get('HISTORY_TEST_DATABASE_URL')
        if not url:
            raise unittest.SkipTest('HISTORY_TEST_DATABASE_URL must point to a separate integration-test database')
        cls.envpatch=unittest.mock.patch.dict(os.environ,{'HISTORY_DATABASE_URL':url})
        cls.envpatch.start()
    @classmethod
    def tearDownClass(cls):
        cls.envpatch.stop()
    def setUp(self):
        migrate()
        self.book='TEST_SYNTHETIC_'+uuid.uuid4().hex
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'fixture.jsonl'
        self.r=fixture(self.book)
        self.path.write_text(json.dumps(self.r,ensure_ascii=False)+'\n',encoding='utf-8')
        self.client=TestClient(app)
    def tearDown(self):
        with connect() as conn:
            conn.execute('DELETE FROM history.chapters WHERE book_id=%s',(self.book,))
            conn.execute('DELETE FROM history.books WHERE book_id=%s',(self.book,))
        self.temp.cleanup()
    def test_import_idempotent_and_read(self):
        import_jsonl(self.path);import_jsonl(self.path)
        r=self.client.get('/search',params={'q':'五年内不加税赋','book_id':self.book})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['items']),1)
        self.assertEqual(r.json()['items'][0]['match_offsets'],[4])
        self.assertEqual(self.client.get('/chapters/'+self.book+':0').json()['original_text'],self.r['text'])
    def test_literal_metacharacters_and_injection(self):
        import_jsonl(self.path)
        self.assertEqual(len(self.client.get('/search',params={'q':'%_\\','book_id':self.book}).json()['items']),1)
        self.assertEqual(self.client.get('/search',params={'q':"' OR 1=1 --",'book_id':self.book}).json()['items'],[])
        self.assertEqual(self.client.get('/search',params={'q':'宣宗','book_id':"' OR 1=1 --"}).json()['items'],[])
    def test_rollback_late_bad_record(self):
        import_jsonl(self.path)
        changed=copy.deepcopy(self.r);changed['chapter_title']='SHOULD ROLLBACK'
        self.path.write_text(json.dumps(changed)+'\n{"schema_version":0}\n',encoding='utf-8')
        with self.assertRaises(ValueError):import_jsonl(self.path)
        row=self.client.get('/chapters/'+self.book+':0').json()
        self.assertEqual(row['title'],self.r['chapter_title'])
    def test_short_search_and_metadata(self):
        import_jsonl(self.path)
        r=self.client.get('/search',params={'q':'五年','book_id':self.book}).json()
        self.assertEqual(r['strategy'],'short_literal_scan')
        self.r.update(text=None,paragraphs=[],verification_status='metadata_only')
        self.path.write_text(json.dumps(self.r),encoding='utf-8')
        import_jsonl(self.path)
        self.assertEqual(self.client.get('/search',params={'q':'五年','book_id':self.book}).json()['items'],[])
    def test_resume_after_x_y_x(self):
        original=self.path.read_bytes()
        x=import_jsonl(self.path)['input_sha256']
        self.assertTrue(already_current(x))
        self.r['chapter_title']='SECOND EXPORT Y'
        self.path.write_text(json.dumps(self.r),encoding='utf-8')
        y=import_jsonl(self.path)['input_sha256']
        self.assertTrue(already_current(y))
        self.assertFalse(already_current(x))
        self.path.write_bytes(original)
        import_jsonl(self.path)
        self.assertTrue(already_current(x))
        self.assertFalse(already_current(y))
    def test_limits_and_health(self):
        self.assertEqual(self.client.get('/search',params={'q':'x','limit':101}).status_code,422)
        self.assertEqual(self.client.get('/health').status_code,200)
        with connect() as conn:
            trigrams=conn.execute('SELECT show_trgm(%s) AS t',('五年内不加税赋',)).fetchone()['t']
        self.assertTrue(trigrams,'Chinese trigram extraction unavailable under this DB locale')

if __name__=='__main__':unittest.main()
