from pathlib import Path
from local_service import Library, HANJI, SOURCES
import json

groups = {
    '主干史书与制度': ['旧唐书','新唐书','资治通鉴','唐会要','唐律疏议','通典'],
    '地理及大型补证': ['元和郡县图志','太平寰宇记','册府元龟'],
    '文学与笔记': ['全唐诗','全唐文','樊川','李义山','樊南','温庭筠','酉阳杂俎','北梦琐言','唐才子传'],
    '生产生活与科技': ['茶经','煎茶水记','酒经','齐民要术','梦溪笔谈','荆楚岁时记','开元礼','农书','饮膳正要','天工开物'],
}
library = Library()
lines = ['# 本机史料收录核查', '', '核查日期：2026-10-19。只读解析本机 `.CAL` 书目及 `.AMG` 篇章标题；未导出正文。', '',
         f'扫描位置：`{HANJI}`。本轮识别{len(library.books)}项书目；这是书库项目数，不等于独立古籍的去重数量。', '',
         '**不能说所有史料都在本机。** “目录已检出”不代表某一版本、某一引句已经校勘；“未匹配”仅表示按下列书名或关键词未匹配，不排除别名、合编或被引材料。', '']
for heading, names in groups.items():
    lines += ['## '+heading, '', '| 查询书名或关键词 | 本机核查结果 |', '|---|---|']
    for name in names:
        found = [b for b in library.books if name in b['title']]
        detail = '；'.join(f"{b['title']}（{b['id']}）" for b in found) or '本轮书目未匹配；保留外部补证入口'
        lines.append(f'| {name} | {detail} |')
    lines.append('')
lines += ['## 阅读器已登记出处', '', f'已登记{len(SOURCES)}个常用卷次，全部匹配到本机篇章标题；原文及自动操作仍待实机核对。', '',
          '| 代号 | 本机书库 | 篇章标题 |', '|---|---|---|']
verified = {}
for key in SOURCES:
    source = library.source(key)
    verified[key] = source
    lines.append(f"| {key} | {source['bookId']} | {source['chapter']} |")
lines += ['', '出土文书原件、考古报告、现代研究论文、地方政府资料，以及尚未匹配的文集等仍需另行核查。酒经、农书、笔记等要再核作者、版本和成书时间，不能因目录有书便全部作为宣宗当时史料。', '',
          '使用方式见[本机阅读器说明](../reader/本机阅读器说明.md)。']
out = Path(__file__).resolve().parent.parent / 'docs' / 'cases' / 'tang-xuanzong' / '唐宣宗_846—859' / '本机史料收录核查.md'
out.write_text('\n'.join(lines)+'\n', encoding='utf-8')
(Path(__file__).resolve().parent / 'catalog-verification.json').write_text(json.dumps({'books':len(library.books),'sources':verified},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'已识别{len(library.books)}项，已核卷次{len(verified)}项；报告：{out}')
