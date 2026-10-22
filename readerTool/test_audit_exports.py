import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from audit_exports import audit


class AuditTests(unittest.TestCase):
    def fixture(self,folder):
        row={'chapter_index':0,'chapter_id':'SYNTHETIC:0','source_sha256':'a'*64,
             'decoder':'synthetic','verification_status':'decoded_unverified',
             'text':'Synthetic\nexample','paragraphs':[{'ordinal':0,'text':'Synthetic'},
             {'ordinal':1,'text':'example'}],
             'metadata':{'dll_sha256':'b'*64,'private_use_count':0,'embedded_object_count':0}}
        path=folder/'SYNTHETIC.jsonl'
        path.write_text(json.dumps(row)+'\n',encoding='utf-8')
        report={'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'source_sha256':'a'*64,'dll_sha256':'b'*64,'decoder':'synthetic',
                'chapters':1,'characters':len(row['text'])}
        path.with_suffix('.report.json').write_text(json.dumps(report),encoding='utf-8')
        return path,row,report

    def test_complete_export_and_ignore_part(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);self.fixture(folder)
            (folder/'unfinished.part.jsonl').write_text('invalid',encoding='utf-8')
            result=audit(folder)
            self.assertEqual(result['errors'],[])
            self.assertEqual(result['totals']['books'],1)
            self.assertEqual(result['totals']['paragraphs'],2)

    def test_output_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path,_,_=self.fixture(folder)
            with path.open('a',encoding='utf-8') as stream: stream.write('tampered')
            result=audit(folder)
            self.assertEqual(result['totals']['books'],0)
            self.assertIn('hash mismatch',result['errors'][0]['error'])

    def test_paragraph_omission_detected_even_if_hash_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path,row,report=self.fixture(folder)
            row['paragraphs'].pop()
            path.write_text(json.dumps(row)+'\n',encoding='utf-8')
            report['output_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_suffix('.report.json').write_text(json.dumps(report),encoding='utf-8')
            result=audit(folder)
            self.assertEqual(result['totals']['text_chapters'],0)
            self.assertIn('coverage mismatch',result['errors'][0]['error'])

if __name__=='__main__':unittest.main()
