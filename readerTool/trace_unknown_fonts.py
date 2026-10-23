"""Trace the exact RTF font state at GBK-extension recovery, without changing text."""
import codecs
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import re
import rtf_text

HERE=Path(__file__).resolve().parent
OUT=HERE/'.local/unknowns'


def font_description(value):
    def recover(match):return bytes.fromhex(match[1]).decode('latin1')
    value=re.sub(r"\\'([0-9a-fA-F]{2})",recover,value)
    value=re.sub(r'\\[a-zA-Z]+-?\d* ?', '', value)
    value=re.sub(r'[{}\\*]', '', value)
    value=value.encode('latin1').decode('gb18030',errors='strict').strip()
    # A 10-byte PANOSE classification is formatting metadata, not the font name.
    return re.sub(r'^[0-9a-fA-F]{20}(?=\D)', '', value)


def main():
    occurrences=[json.loads(line) for line in (OUT/'occurrences.jsonl').open(encoding='utf8')]
    chapter_ids={row['chapter_id'] for row in occurrences}
    expected={}
    for path in (HERE/'.local/exports').glob('*.jsonl'):
        if path.name.endswith('.part.jsonl'):continue
        with path.open(encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line)
                if row['chapter_id'] in chapter_ids:expected[row['chapter_id']]=row
    traces={};context={};failures=[]
    original=rtf_text.gbk_extension

    def trace(error):
        result,end=original(error)
        if not any(0xe000<=ord(c)<=0xf8ff for c in result):return result,end
        frame=inspect.currentframe().f_back
        while frame and frame.f_code.co_name!='rtf_to_text':frame=frame.f_back
        if frame:
            state=frame.f_locals
            font_id=state.get('current_font') or state.get('default_font')
            font=state.get('fonttbl',{}).get(font_id,{})
            prefix=state['out']+error.object[:error.start].decode('gb18030',errors='strict')
            if any(0xd800<=ord(c)<=0xdfff for c in prefix):
                prefix=prefix.encode('utf-16-le',errors='surrogatepass').decode('utf-16-le',errors='strict')
            name=font_description(font.get('name',''))
            key=(context['chapter_id'],len(prefix),f'U+{ord(result):04X}')
            traces[key]={'font_id':font_id,'font_description':name,
                         'rtf_font_name_raw':font.get('name',''),'legacy_bytes':error.object[error.start:end].hex(),
                         'custom_font':bool(re.search(r'ICS\d|CHANT',name,re.I))}
        return result,end

    codecs.register_error('hanji_gbk_extension',trace)
    for i,(cid,row) in enumerate(sorted(expected.items()),1):
        context['chapter_id']=cid
        raw_path=HERE/'.local/raw'/row['book_id']/row['metadata']['raw_file']
        try:
            raw=raw_path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['metadata']['raw_sha256']:raise ValueError('Raw hash mismatch')
            text,_=rtf_text.decode_rtf(raw)
            if text!=row['text']:raise ValueError('Diagnostic decode differs from stored source text')
        except Exception as exc:
            failures.append({'chapter_id':cid,'error':str(exc)})
            # A failed round-trip invalidates ALL partial traces for that chapter.
            for key in [key for key in traces if key[0]==cid]:del traces[key]
        if i%50==0:print(json.dumps({'traced_chapters':i,'total':len(expected)}),flush=True)
    matched=0;fonts=Counter()
    with (OUT/'font-occurrences.jsonl').open('w',encoding='utf8') as stream:
        for row in occurrences:
            found=traces.get((row['chapter_id'],row['offset'],row['codepoint']))
            row['font_trace']=found
            if found:matched+=1;fonts[found['font_description']]+=1
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'occurrences':len(occurrences),'font_traced':matched,'not_traced':len(occurrences)-matched,
            'fonts':dict(fonts),'decode_failures':failures,
            'note':'A missing trace is not a mapping. Text, source files and database are unchanged.'}
    (OUT/'font-trace-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=True))
    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
