"""Read-only structural validation; passing does not verify historical claims."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent


def prose(text):
    text = re.sub(r'^(`{3,}|~{3,}).*?^\1[^\n]*$', '', text, flags=re.M | re.S)
    return re.sub(r'(`+)[^\n]*?\1', '', text)


def document_anchors(text):
    """Match explicit HTML anchors and reader engine's numbered heading IDs."""
    text = prose(text)
    anchors = set(re.findall(r'\bid\s*=\s*["\']([^"\']+)["\']', text, flags=re.I))
    heading_count = len(re.findall(r'^ {0,3}#{1,6}(?:[ \t]+|$)', text, flags=re.M))
    heading_count += len(re.findall(r'^ {0,3}\S[^\n]*\n {0,3}(?:=+|-+)[ \t]*$', text, flags=re.M))
    heading_count += len(re.findall(r'<h[1-6](?:\s[^>]*)?>', text, flags=re.I))
    anchors.update(f'heading-{index}' for index in range(1, heading_count + 1))
    return anchors


def validate(root=ROOT):
    root = Path(root).resolve()
    docs = root / 'docs'
    errors = []
    sources = json.loads((root / 'reader' / 'sources.json').read_text(encoding='utf-8-sig'))
    source_ids = {key.casefold() for key in sources}
    registered = set()

    def add(path, message):
        errors.append({'file': str(path.relative_to(root)), 'message': message})

    def target(owner, href, manifest=False):
        href = unquote(href.strip().strip('<>'))
        if not href:
            return
        parts = urlsplit(href)
        if parts.scheme == 'hanji':
            if parts.netloc.casefold() not in source_ids:
                add(owner, '未登记 hanji 出处：' + parts.netloc)
            return
        if parts.scheme in ('http', 'https', 'mailto'):
            if manifest:
                add(owner, '案例目标必须是 docs 内文档：' + href)
            return
        if parts.scheme or href.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:', href):
            add(owner, '不允许的本机路径或协议：' + href)
            return
        path = (root / parts.path if manifest else owner.parent / parts.path if parts.path else owner).resolve()
        try:
            path.relative_to(docs.resolve())
        except ValueError:
            add(owner, '链接越出 docs：' + href)
            return
        if not path.is_file():
            add(owner, '链接目标不存在：' + href)
        elif manifest and path.suffix.lower() != '.md':
            add(owner, '案例入口须为 Markdown：' + href)
        else:
            if not manifest and path.suffix.lower() == '.md':
                if path not in registered:
                    add(owner, '文档链接未登记到任何案例：' + href)
                if parts.fragment and parts.fragment not in document_anchors(path.read_text(encoding='utf-8-sig')):
                    add(owner, '文档链接 anchor 不存在：' + href)
            return path

    manifest = docs / 'cases.json'
    try:
        cases = json.loads(manifest.read_text(encoding='utf-8-sig'))['cases']
        if not isinstance(cases, list):
            raise ValueError('cases 须为列表')
        registered = { (root / href).resolve() for case in cases
                       for href in case.get('documents', []) if isinstance(href, str) }
        ids = set()
        for case in cases:
            for required in ('id', 'title', 'period', 'startYear', 'endYear', 'entry', 'documents', 'topics'):
                if required not in case:
                    add(manifest, '案例缺少字段：' + required)
            case_id = case.get('id')
            if not isinstance(case_id, str) or not case_id or case_id in ids:
                add(manifest, '案例 ID 无效或重复：' + str(case_id))
            ids.add(case_id if isinstance(case_id, str) else '')
            bounds = (case.get('startYear'), case.get('endYear'))
            bounds_valid = all(type(value) is int for value in bounds)
            if not bounds_valid:
                add(manifest, '案例起止年须为整数：' + str(case_id))
            elif bounds[0] > bounds[1]:
                add(manifest, '案例起止年颠倒：' + str(case_id))
            links = [case.get('entry', '')]
            if not isinstance(case.get('documents', []), list):
                add(manifest, 'documents 须为列表')
                documents = []
            else:
                documents = case.get('documents', [])
                links.extend(documents)
            if case.get('entry') not in documents:
                add(manifest, '案例 entry 不在本案例 documents 中：' + str(case_id))
            if case.get('layoutVersion'):
                schema = json.loads((root / 'makeDocs/case_structure.json').read_text(encoding='utf-8-sig'))
                prefix = 'docs/cases/' + str(case_id) + '/'
                if case['layoutVersion'] != schema['version']:
                    add(manifest, '案例叙事结构版本不匹配：' + str(case_id))
                if case.get('entry') != prefix + '阅读入口.md':
                    add(manifest, '案例入口未采用共同模板：' + str(case_id))
                for item in schema['coreDocuments']:
                    href = prefix + item['path']
                    if href not in documents:
                        add(manifest, '缺少共同主干文档：' + href)
                    else:
                        path = target(manifest, href, manifest=True)
                        if path and not prose(path.read_text(encoding='utf-8-sig')).strip():
                            add(path, '共同主干文档为空，不能充作专题完成')
                groups = case.get('documentGroups', [])
                grouped = []
                if not isinstance(groups, list) or not groups:
                    add(manifest, '叙事案例缺少文档分组：' + str(case_id))
                    groups = []
                for group in groups:
                    if not isinstance(group, dict) or not isinstance(group.get('documents'), list) or not group.get('title'):
                        add(manifest, '文档分组格式无效：' + str(case_id))
                        continue
                    grouped.extend(group['documents'])
                if len(grouped) != len(set(grouped)) or set(grouped) != set(documents):
                    add(manifest, '分组须完整且不重复覆盖 documents：' + str(case_id))
                for item in schema['coreDocuments']:
                    if not any(g.get('title') == item['group'] and prefix + item['path'] in g.get('documents', [])
                               for g in groups if isinstance(g, dict)):
                        add(manifest, '主干文档分组与模板不一致：' + item['path'])
                coverage = root / prefix / '史料与考证/研究维度覆盖.md'
                if coverage.is_file():
                    coverage_text = coverage.read_text(encoding='utf-8-sig')
                    for dimension in schema['dimensions']:
                        if not re.search(r'^\|\s*' + re.escape(dimension) + r'\s*\|', coverage_text, re.M):
                            add(coverage, '未记录研究维度：' + dimension)
                aliases = case.get('legacyPaths', {})
                if not isinstance(aliases, dict):
                    add(manifest, 'legacyPaths 须为对象：' + str(case_id))
                else:
                    for old, new in aliases.items():
                        if not isinstance(old, str) or not old.startswith(prefix) or '..' in old.split('/') or '\\' in old or new not in documents:
                            add(manifest, '旧路径映射越界或目标无效：' + str(old))
            sections = case.get('sections', [])
            if not isinstance(sections, list):
                add(manifest, 'sections 须为列表：' + str(case_id))
                sections = []
            section_ids = set()
            for section in sections:
                if not isinstance(section, dict):
                    add(manifest, '分期项须为对象：' + str(case_id))
                    continue
                for required in ('id', 'title', 'startYear', 'endYear'):
                    if required not in section:
                        add(manifest, '分期缺少字段：' + required)
                sid = section.get('id')
                if not isinstance(sid, str) or not sid or sid in section_ids:
                    add(manifest, '分期 ID 无效或重复：' + str(sid))
                section_ids.add(sid if isinstance(sid, str) else '')
                if not isinstance(section.get('title'), str) or not section['title'].strip():
                    add(manifest, '分期 title 须为非空文字：' + str(sid))
                start, end = section.get('startYear'), section.get('endYear')
                if type(start) is not int or type(end) is not int:
                    add(manifest, '分期起止年须为整数：' + str(sid))
                elif start > end:
                    add(manifest, '分期起止年颠倒：' + str(sid))
                elif bounds_valid and not (bounds[0] <= start <= end <= bounds[1]):
                    add(manifest, '分期超出案例年份范围：' + str(sid))
            years = case.get('years', [])
            if not isinstance(years, list):
                add(manifest, 'years 须为列表：' + str(case_id))
                years = []
            seen_years = set()
            for year in years:
                if not isinstance(year, dict):
                    add(manifest, '纪年项须为对象：' + str(case_id))
                    continue
                value = year.get('year')
                if type(value) is not int:
                    add(manifest, '导航 year 须为整数：' + str(value))
                else:
                    if value in seen_years:
                        add(manifest, '导航年份重复：' + str(value))
                    seen_years.add(value)
                    if bounds_valid and not bounds[0] <= value <= bounds[1]:
                        add(manifest, '导航年份超出案例范围：' + str(value))
                href = year.get('doc', '')
                links.append(href)
                if href not in documents:
                    add(manifest, 'years.doc 不在本案例 documents 中：' + str(href))
                if 'anchor' in year:
                    anchor = year['anchor']
                    if not isinstance(anchor, str) or not anchor.strip():
                        add(manifest, '导航 anchor 须为非空文字：' + str(value))
                    elif isinstance(href, str) and href:
                        path = target(manifest, href, manifest=True)
                        if path and path.suffix.lower() == '.md' and unquote(anchor) not in document_anchors(path.read_text(encoding='utf-8-sig')):
                            add(manifest, '导航 anchor 不存在：' + href + '#' + anchor)
            for href in links:
                if not isinstance(href, str) or not href:
                    add(manifest, '案例文档路径为空或类型错误')
                else:
                    target(manifest, href, manifest=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        add(manifest, '案例清单无效：' + str(error))

    files = sorted(docs.rglob('*.md'))
    for path in files:
        text = prose(path.read_text(encoding='utf-8-sig'))
        definitions = re.findall(r'^\[\^([^\]]+)\]:', text, flags=re.M)
        refs = re.findall(r'\[\^([^\]]+)\](?!:)', text)
        for item in set(definitions):
            if definitions.count(item) > 1:
                add(path, '脚注重复定义：' + item)
        for item in sorted(set(refs) - set(definitions)):
            add(path, '脚注缺少定义：' + item)
        for match in re.finditer(r'!?\[[^\]\n]*\]\((<[^>]*>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\)', text):
            target(path, match.group(1))
        for match in re.finditer(r'^\[(?!\^)[^\]]+\]:\s*(<[^>]*>|\S+)', text, flags=re.M):
            target(path, match.group(1))
    return {'ok': not errors, 'documents': len(files), 'errors': errors,
            'scope': '只校验文档结构、路径、脚注与登记出处；不代表正文或历史事实已核验'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='输出机器可读诊断')
    args = parser.parse_args()
    result = validate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"检查 {result['documents']} 篇文档，发现 {len(result['errors'])} 项结构问题。")
        for error in result['errors']:
            print(error['file'] + ': ' + error['message'])
        print(result['scope'])
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
