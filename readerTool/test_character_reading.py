import copy
import hashlib
import unittest
from character_reading import reading_view


class CharacterReadingTests(unittest.TestCase):
    def fixture(self):
        text='SYNTHETIC \U00020000\ue864'
        chapter={'chapter_id':'SYNTHETIC:0','original_text':text,'source_sha256':'a'*64,'decoder':'synthetic'}
        note={'codepoint':'U+E864','offset':len(text)-1,
              'font_trace':{'font_description':'宋体','legacy_bytes':'fea0','custom_font':False}}
        record={'chapter_id':chapter['chapter_id'],'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'source_sha256':chapter['source_sha256'],'decoder':chapter['decoder'],'notes':[note]}
        return chapter,record

    def test_reading_layer_preserves_original_and_offsets(self):
        chapter,record=self.fixture();before=copy.deepcopy(chapter)
        result=reading_view(chapter,record)
        self.assertEqual(result['reading_text'],'SYNTHETIC \U00020000\u9fbb')
        self.assertEqual(result['replacements_applied'],1)
        self.assertEqual(chapter,before)
        self.assertEqual(result['original_text'],before['original_text'])

    def test_same_code_in_ics_font_is_not_replaced(self):
        chapter,record=self.fixture()
        record['notes'][0]['font_trace'].update(font_description='ICS7',custom_font=True)
        result=reading_view(chapter,record)
        self.assertEqual(result['reading_text'],chapter['original_text'])
        self.assertEqual(result['notes'][0]['status'],'custom_font_missing')

    def test_unmatched_bytes_are_not_replaced(self):
        chapter,record=self.fixture();record['notes'][0]['font_trace']['legacy_bytes']='aaaa'
        self.assertEqual(reading_view(chapter,record)['replacements_applied'],0)

    def test_custom_font_name_containing_simsun_is_not_trusted(self):
        chapter,record=self.fixture()
        record['notes'][0]['font_trace']['font_description']='Vendor SimSun CustomGlyph'
        self.assertEqual(reading_view(chapter,record)['replacements_applied'],0)

    def test_stale_text_or_source_rejected(self):
        for key,value in [('original_text','changed'),('source_sha256','b'*64),('decoder','different')]:
            chapter,record=self.fixture();chapter[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reading_view(chapter,record)

    def test_wrong_offsets_rejected(self):
        chapter,record=self.fixture();record['notes'][0]['offset']=0
        with self.assertRaises(ValueError):reading_view(chapter,record)

    def test_no_body_or_no_report_does_not_invent_text(self):
        chapter,_=self.fixture()
        self.assertEqual(reading_view(chapter,None)['reading_text'],chapter['original_text'])
        chapter['original_text']=None
        self.assertIsNone(reading_view(chapter,None)['reading_text'])

if __name__=='__main__':unittest.main()
