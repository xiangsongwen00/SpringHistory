"""Synthetic resources only. No corpus data is embedded in tests."""
import hashlib
import unittest
from rtf_assets import extract_assets


class AssetTests(unittest.TestCase):
    def test_nested_fallback_and_exact_byte_ranges(self):
        raw=br'{\rtf1 x {\object{\*\objdata abcd}{\result{\pict\pngblip 89504e47}}}y}'
        assets=extract_assets(raw)
        self.assertEqual([a['kind'] for a in assets],['object','pict'])
        self.assertEqual(assets[1]['parent_ordinal'],0)
        self.assertEqual(assets[1]['payload'],bytes.fromhex('89504e47'))
        for a in assets:
            self.assertEqual(a['raw_group'],raw[a['start']:a['end']])
            self.assertEqual(a['raw_group_sha256'],hashlib.sha256(a['raw_group']).hexdigest())

    def test_property_text_excluded(self):
        a=extract_assets(br'{\rtf1{\pict{\*\picprop{\sn abcd}{\sv 99}}\wmetafile8 0102 0304}}')[0]
        self.assertEqual(a['payload'],b'\x01\x02\x03\x04')
        self.assertEqual(a['format'],'wmf')

    def test_invalid_or_ambiguous_hex_preserved(self):
        for body in (b'abc',b'not_hex'):
            a=extract_assets(b'{\\rtf1{\\pict '+body+b'}}')[0]
            self.assertIsNone(a['payload'])
            self.assertEqual(a['status'],'raw_group_preserved')

    def test_escaped_braces_are_not_groups(self):
        self.assertEqual(extract_assets(br'{\rtf1 \{\pict\} hello}'),[])

    def test_binary_and_truncation_rejected(self):
        for raw in (br'{\rtf1{\pict',br'{\rtf1{\pict\bin4 abcd}}',br'{\rtf1}}'):
            with self.assertRaises(ValueError):extract_assets(raw)

if __name__=='__main__':unittest.main()
