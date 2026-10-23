"""Synthetic evidence only; no production writes in unit tests."""
import copy
import hashlib
import unittest
from unittest.mock import patch
from restore_corpus import paragraph_digest
from historysys.characters import chapter_characters


class RestorationTests(unittest.TestCase):
    def test_paragraph_digest_includes_order_ordinal_and_normalized(self):
        source=[(0,'甲','甲'),(2,'乙','乙')]
        baseline=paragraph_digest(source)
        for changed in (list(reversed(source)),[(1,'甲','甲'),source[1]],
                        [(0,'甲','改'),source[1]],[(0,'改','甲'),source[1]],source[:1]):
            self.assertNotEqual(baseline,paragraph_digest(changed))
        self.assertEqual(baseline,paragraph_digest(iter(source)))

    def test_database_notes_work_without_local_file(self):
        text='合成\ue864记录'
        chapter={'chapter_id':'SYNTHETIC:0','original_text':text,'source_sha256':'0'*64,
                 'decoder':'synthetic-v1','verification_status':'decoded_unverified'}
        record={'chapter_id':chapter['chapter_id'],'source_sha256':chapter['source_sha256'],
                'decoder':chapter['decoder'],'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'notes':[{'offset':2,'codepoint':'U+E864',
                          'font_trace':{'font_description':'宋体','legacy_bytes':'fea0','custom_font':False}}]}
        with patch('historysys.characters.NOTES') as path:
            path.is_file.side_effect=AssertionError('Database branch should not read local report')
            result=chapter_characters(chapter,record)
        self.assertEqual(result['original_text'],text)
        self.assertEqual(result['reading_text'],'合成龻记录')
        self.assertEqual(result['character_record_storage'],'postgresql')
        stale=copy.deepcopy(chapter);stale['original_text']+='变'
        with self.assertRaises(ValueError):chapter_characters(stale,record)

if __name__=='__main__':unittest.main()
