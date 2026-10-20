"""Tests use temporary documents and mocked HTTP; never operate native windows."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import query_source
from validate_docs import validate


class DocumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'docs').mkdir()
        (self.root / 'reader').mkdir()
        (self.root / 'reader/sources.json').write_text('{"J18":{}}', encoding='utf-8')
        (self.root / 'docs/cases.json').write_text(json.dumps({'cases': [{
            'id': 'test', 'title': 'Test', 'period': '唐', 'startYear': 846, 'endYear': 859,
            'entry': 'docs/entry.md', 'documents': ['docs/entry.md'], 'topics': ['土地']}]}), encoding='utf-8')
        self.doc = self.root / 'docs/entry.md'

    def test_valid_and_code_examples_ignored(self):
        self.doc.write_text('正文[^a]\n\n[^a]: [查原文](hanji://J18?q=土地)\n\n```md\n[例](../private.md)\n```', encoding='utf-8')
        self.assertTrue(validate(self.root)['ok'])

    def test_escaping_link_and_unknown_source(self):
        self.doc.write_text('[越界](../secret.md) [未知](hanji://BAD)', encoding='utf-8')
        messages = [e['message'] for e in validate(self.root)['errors']]
        self.assertTrue(any('越出 docs' in m for m in messages))
        self.assertTrue(any('未登记' in m for m in messages))

    def test_missing_and_duplicate_footnotes(self):
        self.doc.write_text('内容[^missing]\n\n[^a]: 一\n[^a]: 二', encoding='utf-8')
        messages = [e['message'] for e in validate(self.root)['errors']]
        self.assertTrue(any('缺少定义' in m for m in messages))
        self.assertTrue(any('重复定义' in m for m in messages))

    def test_missing_manifest_document(self):
        self.assertTrue(any('不存在' in e['message'] for e in validate(self.root)['errors']))

    def change_case(self, **values):
        path = self.root / 'docs/cases.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['cases'][0].update(values)
        path.write_text(json.dumps(manifest), encoding='utf-8')

    def messages(self):
        return [error['message'] for error in validate(self.root)['errors']]

    def test_navigation_membership_required(self):
        self.doc.write_text('# 入口', encoding='utf-8')
        (self.root / 'docs/other.md').write_text('# 外部条目', encoding='utf-8')
        self.change_case(entry='docs/other.md', years=[{'year': 846, 'doc': 'docs/other.md'}])
        messages = self.messages()
        self.assertTrue(any('entry 不在' in message for message in messages))
        self.assertTrue(any('years.doc 不在' in message for message in messages))

    def test_explicit_and_numbered_heading_anchors(self):
        self.doc.write_text('# 入口\n\n<a id="year-846"></a>\n\n## 次标题\n\nSetext\n===\n', encoding='utf-8')
        self.change_case(years=[{'year': 846, 'doc': 'docs/entry.md', 'anchor': 'year-846'},
                                {'year': 847, 'doc': 'docs/entry.md', 'anchor': 'heading-2'},
                                {'year': 848, 'doc': 'docs/entry.md', 'anchor': 'heading-3'}],
                         sections=[{'id': 'early', 'title': '前期', 'startYear': 846, 'endYear': 850}])
        self.assertTrue(validate(self.root)['ok'], self.messages())

    def test_missing_anchor_and_out_of_range_year(self):
        self.doc.write_text('# 入口\n\n```html\n<a id="fake"></a>\n```', encoding='utf-8')
        self.change_case(years=[{'year': 900, 'doc': 'docs/entry.md', 'anchor': 'fake'}])
        messages = self.messages()
        self.assertTrue(any('anchor 不存在' in message for message in messages))
        self.assertTrue(any('年份超出' in message for message in messages))

    def test_section_ids_fields_and_ranges(self):
        self.doc.write_text('# 入口', encoding='utf-8')
        self.change_case(sections=[{'id': 'a', 'title': '早期', 'startYear': 845, 'endYear': 850},
                                   {'id': 'a', 'title': '反向', 'startYear': 855, 'endYear': 850},
                                   {'id': 'missing'}])
        messages = self.messages()
        self.assertTrue(any('分期 ID 无效或重复' in message for message in messages))
        self.assertTrue(any('分期超出' in message for message in messages))
        self.assertTrue(any('分期起止年颠倒' in message for message in messages))
        self.assertTrue(any('分期缺少字段' in message for message in messages))

    def test_year_and_section_types_checked(self):
        self.doc.write_text('# 入口', encoding='utf-8')
        self.change_case(startYear='846', years=[{'year': True, 'doc': 'docs/entry.md'}],
                         sections=[{'id': 'a', 'title': '', 'startYear': '846', 'endYear': 850}])
        messages = self.messages()
        self.assertTrue(any('案例起止年须为整数' in message for message in messages))
        self.assertTrue(any('导航 year 须为整数' in message for message in messages))
        self.assertTrue(any('分期起止年须为整数' in message for message in messages))


class QueryTests(unittest.TestCase):
    def args(self, **values):
        args = dict(base='http://127.0.0.1:18865', source='J18', open=False, query=None, mode='auto', timeout=1)
        args.update(values)
        return SimpleNamespace(**args)

    def test_nonlocal_service_rejected(self):
        with self.assertRaises(ValueError):
            query_source.run(self.args(base='http://example.com'))

    def test_default_only_reads_source(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return b'{"id":"J18","textVerified":false}'
        with patch.object(query_source, 'build_opener') as factory:
            factory.return_value.open.return_value = Response()
            result, code = query_source.run(self.args())
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:18865/api/source/J18')
            self.assertIsNone(request.data)
            self.assertEqual(factory.return_value.open.call_count, 1)
            self.assertEqual(code, 0)
            self.assertEqual(result['action'], 'resolve_only')
            self.assertFalse(result['source']['textVerified'])


if __name__ == '__main__':
    unittest.main()
