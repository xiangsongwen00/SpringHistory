"""Generate source-bound character annotations and a standalone review page."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from character_reading import reading_view,MAP

HERE=Path(__file__).resolve().parent
OUT=HERE/'.local/unknowns'


def main():
    trace_report=json.loads((OUT/'font-trace-report.json').read_text(encoding='utf8'))
    if trace_report['decode_failures']:raise ValueError('Font tracing contains failed source round-trips; resolve them first')
    groups=defaultdict(list)
    for line in (OUT/'font-occurrences.jsonl').open(encoding='utf8'):
        row=json.loads(line);groups[row['chapter_id']].append(row)
    if sum(map(len,groups.values()))!=trace_report['occurrences']:
        raise ValueError('Font trace report and occurrence file disagree')
    records={};rows=[];totals=Counter();input_hashes={}
    for path in (HERE/'.local/exports').glob('*.jsonl'):
        if path.name.endswith('.part.jsonl'):continue
        with path.open('rb') as stream:input_hashes[path.name]=hashlib.file_digest(stream,'sha256').hexdigest()
        with path.open(encoding='utf8') as stream:
            for line in stream:
                chapter=json.loads(line);cid=chapter['chapter_id']
                if cid not in groups:continue
                record={'chapter_id':cid,'source_sha256':chapter['source_sha256'],'decoder':chapter['decoder'],
                        'text_sha256':hashlib.sha256(chapter['text'].encode('utf8')).hexdigest(),'notes':groups[cid]}
                view=reading_view(dict(chapter,original_text=chapter['text']),record)
                record['notes']=view['notes'];records[cid]=record
                rows.extend(view['notes']);totals.update(n['status'] for n in view['notes'])
    if set(records)!=set(groups):raise ValueError('Some character records have no matching exported chapter')
    report={'mapping_version':MAP['version'],'mapping_source':MAP['source_url'],
            'source_exports_sha256':input_hashes,'affected_chapters':len(records),
            'private_use_occurrences':len(rows),'statuses':dict(totals),'chapters':records,
            'original_unchanged':True}
    part=OUT/'chapter-notes.part.json';part.write_text(json.dumps(report,ensure_ascii=False),encoding='utf8')
    part.replace(OUT/'chapter-notes.json')
    data=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    summary=json.dumps({'总记录':len(rows),'已核编码映射':totals['encoding_mapping_verified'],
                        '缺ICS字体':totals['custom_font_missing'],'其他待核':totals['unresolved']},ensure_ascii=False)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>未知字符核对记录</title>
<style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;margin:28px;color:#23303d;background:#f7f9fc}h1{font-size:26px}input,select,button{font:inherit;padding:8px;margin:5px}article{background:white;padding:18px;margin:14px 0;border:1px solid #dce2e9;border-radius:8px}small{color:#586879}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.8 "SimSun",serif}.ok{color:#146b42}.pending{color:#975c13}code{font-family:monospace}</style>
<h1>未知字符核对记录</h1><p>保留原文，按字体与原始字节核对；已核“编码映射”不等于已完成历史校勘。</p>
<p id="summary"></p><p>ICS7 与方正字库不是同一码表。未取得原字库或可靠映射时，不用其他字体显示的字形替换。</p>
<input id="q" placeholder="书名、章ID、码位或上下文" size="40"><select id="status"><option value="">全部状态</option><option value="encoding_mapping_verified">已核编码映射</option><option value="custom_font_missing">缺ICS字体</option><option value="unresolved">其他待核</option></select>
<button id="prev">上一页</button><button id="next">下一页</button><span id="count"></span><main id="results"></main>
<script type="application/json" id="records">__DATA__</script><script>
const data=JSON.parse(document.getElementById('records').textContent);let page=0;const size=30;
document.getElementById('summary').textContent=__SUMMARY__;
function shown(s){return [...s].map(c=>{let n=c.codePointAt(0);return (n>=0xe000&&n<=0xf8ff)||(n>=0xf0000&&n<=0x10fffd)?'['+'U+'+n.toString(16).toUpperCase()+']':c}).join('')}
function add(parent,tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;parent.appendChild(e);return e}
function render(){const query=document.getElementById('q').value.toLowerCase(),status=document.getElementById('status').value;
const found=data.filter(r=>(!status||r.status===status)&&[r.book_title,r.chapter_title,r.chapter_id,r.codepoint,r.context,r.replacement||''].join(' ').toLowerCase().includes(query));
page=Math.max(0,Math.min(page,Math.ceil(found.length/size)-1));document.getElementById('count').textContent=`${found.length} 条 · 第 ${page+1} 页`;const root=document.getElementById('results');root.replaceChildren();
for(const r of found.slice(page*size,(page+1)*size)){const card=document.createElement('article');root.appendChild(card);const ok=r.status==='encoding_mapping_verified';
add(card,'strong',`${r.codepoint} ${ok?' → '+r.replacement+' '+r.target_codepoint:' · 待核'}`,ok?'ok':'pending');
add(card,'div',r.book_title+' · '+r.chapter_title);add(card,'small',r.chapter_id+' · 原文字位 '+r.offset+' · 字体 '+(r.font_trace?.font_description||'未追踪')+' · 原字节 '+(r.font_trace?.legacy_bytes||'未知'));
add(card,'pre','原文：'+shown(r.context));if(ok){const reading=[...r.context],center=Math.min(24,r.offset);reading[center]=r.replacement;add(card,'pre','阅读视图：'+shown(reading.join('')));add(card,'div','已核依据：Unicode ICU标准映射 + 原始字节 + 非ICS宋体状态；仅应用于独立阅读视图。','ok');}
add(card,'small','AMG SHA256 '+r.source_sha256+' · RTF SHA256 '+r.raw_rtf_sha256);}}
for(const id of ['q','status'])document.getElementById(id).oninput=()=>{page=0;render()};document.getElementById('prev').onclick=()=>{page--;render()};document.getElementById('next').onclick=()=>{page++;render()};render();</script></html>'''
    page=page.replace('__DATA__',data).replace('__SUMMARY__',json.dumps(summary,ensure_ascii=False))
    (OUT/'review.html').write_text(page,encoding='utf8')
    print(json.dumps({'affected_chapters':len(records),'occurrences':len(rows),'statuses':dict(totals),'original_unchanged':True}))

if __name__=='__main__':main()
