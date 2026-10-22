"""Synthetic RTF fixtures; no historical quotations or library files."""
import unittest
from rtf_text import decode_rtf


class RtfTests(unittest.TestCase):
    def test_mixed_gbk_literal_trail(self):
        text,meta=decode_rtf(br"{\rtf1\ansi\ansicpg936 \'b5y}")
        self.assertEqual(text,bytes.fromhex('b579').decode('gbk'))
        self.assertEqual(meta['replacement_count'],0)

    def test_extended_pair_is_audited(self):
        text,meta=decode_rtf(br"{\rtf1\ansi\ansicpg936 \'a9\'89}")
        self.assertEqual(text,'\u303e')
        self.assertEqual(meta['gb18030_extension_count'],1)
        self.assertEqual(meta['gb18030_extensions'][0]['bytes'],'a989')

    def test_escaped_gbk_trail_brace(self):
        text,_=decode_rtf(br"{\rtf1\ansicpg936 \'b5\}}")
        self.assertEqual(text,bytes.fromhex('b57d').decode('gbk'))

    def test_font_semicolons_remain_parseable(self):
        fonts=''.join('{\\f%d\\fcharset134 Synthetic;}'%i for i in range(80))
        raw=('{\\rtf1\\ansicpg936{\\fonttbl'+fonts+'}\\f1 Sample;}').encode('ascii')
        self.assertEqual(decode_rtf(raw)[0],'Sample;')

    def test_unicode_fallback(self):
        self.assertEqual(decode_rtf(br'{\rtf1\uc1\u20013?}')[0],'\u4e2d')

    def test_bad_encoding_and_structure_quarantined(self):
        for raw in (br"{\rtf1\ansicpg936 \'a9\'ff}",br'{\rtf1\ansicpg99999 abc}',
                    br'{\rtf1 missing',br'{\rtf1}}',br'{\rtf1\bin1 x}',b'plain',
                    br'{\rtf1 Body{\footnote Note}}',br'{\rtf1 Body{\*\annotation Note}}'):
            with self.subTest(raw=raw),self.assertRaises((ValueError,LookupError)):
                decode_rtf(raw)

if __name__=='__main__': unittest.main()
