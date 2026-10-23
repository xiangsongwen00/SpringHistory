import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from text_bridge import endpoint,source_reference,TextServiceError
import launch_reader


class TextBridgeTests(unittest.TestCase):
    def test_fixed_read_only_allowlist(self):
        self.assertEqual(endpoint('/search','q=%E5%BA%9E%E5%8B%8B&limit=20'),'/search?q=%E5%BA%9E%E5%8B%8B&limit=20')
        self.assertEqual(endpoint('/chapters/B01-137:21/assets/0/download','part=raw'),'/chapters/B01-137:21/assets/0/download?part=raw')
        for path,query in [('/../health',''),('//other-host',''),('/search','url=http://example.org'),
                           ('/search','q=a&q=b'),('/chapters/../../x','')]:
            with self.assertRaises(TextServiceError):endpoint(path,query)

    def test_resolve_actual_chapter_and_reject_ambiguous_volume(self):
        sources={'S':{'book':'旧唐书','volume':'19上','label':'synthetic','query':'test'}}
        rows=[{'chapter_id':'B01-137:21','title':'卷十九上'}]
        chapter={'chapter_id':'B01-137:21','title':'卷十九上','source_sha256':'0'*64,
                 'decoder':'synthetic','verification_status':'decoded_unverified'}
        with patch('text_bridge.text_json',side_effect=[rows,chapter]):
            self.assertEqual(source_reference('S',sources)['chapterId'],'B01-137:21')
        with patch('text_bridge.text_json',return_value=rows*2):
            with self.assertRaises(TextServiceError):source_reference('S',sources)

    def test_explicit_chapter_cannot_point_to_another_book(self):
        source={'S':{'book':'旧唐书','bookId':'B01-137','chapterId':'OTHER:0'}}
        with patch('text_bridge.text_json',return_value={'book_id':'OTHER'}):
            with self.assertRaises(TextServiceError):source_reference('S',source)

    def test_named_chapter_requires_exact_database_title(self):
        sources={'S':{'book':'茶经','bookId':'C03-396','chapterId':'C03-396:2',
                      'volume':'三之造','chapterTitle':'茶经·三之造','nativeAvailable':False}}
        chapter={'book_id':'C03-396','chapter_id':'C03-396:2','title':'茶经·三之造',
                 'source_sha256':'0'*64,'decoder':'synthetic','verification_status':'decoded_unverified'}
        with patch('text_bridge.text_json',return_value=chapter):
            self.assertEqual(source_reference('S',sources)['chapterId'],'C03-396:2')
        with patch('text_bridge.text_json',return_value={**chapter,'title':'茶经·二之具'}):
            with self.assertRaises(TextServiceError):source_reference('S',sources)

    def test_reader_starts_only_existing_database_api_launcher(self):
        with patch('launch_reader.subprocess.run') as run,patch('pathlib.Path.is_file',return_value=True):
            run.return_value.returncode=0
            self.assertTrue(launch_reader.ensure_text_service())
            command=run.call_args.args[0]
            self.assertTrue(command[1].endswith('launch_service.py'))
            self.assertEqual(command[2],'--no-browser')
            self.assertNotIn('init_local',str(command))

if __name__=='__main__':unittest.main()
