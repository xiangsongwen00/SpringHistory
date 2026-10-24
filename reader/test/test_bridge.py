import json
from pathlib import Path
import sys
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hanji_catalog import volume_key, find_chapter
from local_service import Library, SOURCES, AppState, make_handler, load_docs, load_cases


class CatalogueTests(unittest.TestCase):
    def test_moved_case_accepts_explicit_old_root_and_rejects_traversal(self):
        new='docs/cases/背景综述/晚唐时期背景综述/阅读入口.md'
        old='docs/cases/晚唐时期背景制度综述/阅读入口.md'
        case={'id':'background','root':new.rsplit('/',1)[0]+'/',
              'entry':new,'documents':[new],
              'legacyRoots':['docs/cases/晚唐时期背景制度综述/'],
              'legacyPaths':{old:new}}
        with TemporaryDirectory() as tmp, patch('local_service.DOCS_ROOT',Path(tmp)):
            p=Path(tmp)/'cases.json'
            p.write_text(json.dumps({'cases':[case]}),encoding='utf8')
            self.assertEqual(load_cases([{'path':new}])[0]['id'],'background')
            case['legacyRoots']=['docs/cases/../../private/']
            p.write_text(json.dumps({'cases':[case]}),encoding='utf8')
            with self.assertRaises(ValueError):load_cases([{'path':new}])

    def test_volume_variants(self):
        for title in ['卷第二百四十八', '卷二四八', '卷248']:
            self.assertEqual(volume_key(title), (248, ''))
        self.assertEqual(volume_key('旧唐书卷一九○下'), (190, '下'))
        self.assertEqual(volume_key('新唐书卷四〇'), (40, ''))

    def test_ambiguous_chapter_stops(self):
        with self.assertRaises(ValueError):
            find_chapter([{'title':'卷十八下'}, {'title':'卷一八下'}], '18下')

    def test_all_registered_sources_exist_locally(self):
        library = Library()
        self.assertGreater(len(library.books), 800)
        for key in SOURCES:
            source = library.source(key)
            if SOURCES[key].get('nativeAvailable') is False:
                self.assertFalse(source['catalogueVerified'], key)
                self.assertTrue(source['bookCatalogueVerified'], key)
                self.assertIsNone(source['chapterIndex'], key)
                self.assertTrue(SOURCES[key]['chapterId'], key)
            else:
                self.assertTrue(source['catalogueVerified'], key)
            self.assertFalse(source['textVerified'], key)
            self.assertFalse(source['automationVerified'], key)

    def test_reading_documents_include_workspace(self):
        docs = load_docs()
        self.assertTrue(any('/年事/' in d['path'] for d in docs))
        self.assertTrue(any('/纪传体/' in d['path'] for d in docs))
        self.assertTrue(all(d['path'].startswith('docs/') for d in docs))
        self.assertTrue(any('[^河陇]' in d['content'] for d in docs))
        self.assertFalse(any('.venv' in d['path'] for d in docs))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        def fake(*args):
            cls.calls.append(args)
            return {'stage':'query_sent', 'message':'mock: no desktop input'}
        cls.state = AppState(Library(), 0, driver=fake)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.state))
        cls.state.origin = f'http://127.0.0.1:{cls.server.server_port}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.state.executor.shutdown()

    def fetch(self, path, body=None, headers=None):
        request = urllib.request.Request(self.state.origin + path,
            data=None if body is None else json.dumps(body).encode(), headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def authorized(self):
        return {'Origin':self.state.origin, 'X-Reader-Token':self.state.token,
                'Content-Type':'application/json'}

    def test_bootstrap_and_resolve(self):
        status, body = self.fetch('/api/source/J18')
        self.assertEqual(status, 200)
        self.assertIn('一八下', json.loads(body)['chapter'])
        status, body = self.fetch('/api/bootstrap')
        self.assertEqual(status, 200)
        self.assertIn('token', json.loads(body))

    def test_reject_foreign_origin_and_missing_token(self):
        for headers in [{}, {'Origin':'https://example.org','X-Reader-Token':self.state.token}]:
            self.assertEqual(self.fetch('/api/open', {'sourceId':'J18'}, headers)[0], 403)

    def test_reject_unknown_source_and_command_modes(self):
        for body in [{'sourceId':'../../1.exe'}, {'sourceId':'J18','mode':'powershell'},
                     {'sourceId':'J18','query':'abc\nnext'}, {'sourceId':'J18','query':'a'*121}]:
            self.assertEqual(self.fetch('/api/open', body, self.authorized())[0], 400)

    def test_private_files_not_served(self):
        for path in ['/../local_service.py', '/%2e%2e/sources.json', '/.venv/pyvenv.cfg', '/api/chapters/../../1']:
            self.assertEqual(self.fetch(path)[0], 404)

    def test_driver_job_with_fake_adapter(self):
        status, body = self.fetch('/api/open', {'sourceId':'X54','query':'宣宗','mode':'auto'}, self.authorized())
        self.assertEqual(status, 202)
        job_id = json.loads(body)['id']
        for _ in range(50):
            job = json.loads(self.fetch('/api/job/'+job_id)[1])
            if job['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(job['state'], 'done')
        self.assertFalse(job['textVerified'])
        self.assertEqual(job['stage'], 'query_sent')
        self.assertEqual(self.calls[-1][4], '宣宗')


if __name__ == '__main__':
    unittest.main()
