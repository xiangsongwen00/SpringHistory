"""Read-only census of private-use codepoints, with byte-preserving evidence."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
PUA=re.compile('[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]')
CONTROL=re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exports',type=Path,default=HERE/'.local/exports')
    parser.add_argument('--output',type=Path,default=HERE/'.local/unknowns')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    counts=Counter();controls=Counter();samples=defaultdict(list);books=defaultdict(set)
    chapters=set();records=0
    with (args.output/'occurrences.jsonl').open('w',encoding='utf8') as output:
        for path in sorted(args.exports.glob('*.jsonl')):
            if path.name.endswith('.part.jsonl'):continue
            with path.open(encoding='utf8') as stream:
                for line in stream:
                    row=json.loads(line);text=row.get('text') or '';records+=1
                    controls.update(f'U+{ord(m.group()):04X}' for m in CONTROL.finditer(text))
                    for match in PUA.finditer(text):
                        char=match.group();code=f'U+{ord(char):04X}';pos=match.start()
                        counts[code]+=1;books[code].add(row['book_id']);chapters.add(row['chapter_id'])
                        evidence={'codepoint':code,'book_id':row['book_id'],'book_title':row['book_title'],
                                  'chapter_id':row['chapter_id'],'chapter_title':row['chapter_title'],
                                  'offset':pos,'context':text[max(0,pos-24):pos+25],
                                  'source_sha256':row['source_sha256'],'decoder':row['decoder'],
                                  'raw_rtf_sha256':row['metadata']['raw_sha256']}
                        output.write(json.dumps(evidence,ensure_ascii=False)+'\n')
                        if len(samples[code])<5:samples[code].append(evidence)
    entries=[]
    for code,count in counts.most_common():
        char=chr(int(code[2:],16))
        try: encoded=char.encode('gb18030').hex()
        except UnicodeEncodeError:encoded=None
        entries.append({'codepoint':code,'occurrences':count,'books':len(books[code]),
                        'python_gb18030_bytes':encoded,'samples':samples[code]})
    report={'records_scanned':records,'private_use_occurrences':sum(counts.values()),
            'distinct_codepoints':len(counts),'affected_chapters':len(chapters),
            'control_characters':dict(controls),'entries':entries,
            'note':'Evidence only; no replacement or historical verification is performed.'}
    (args.output/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='entries'}))

if __name__=='__main__':main()
