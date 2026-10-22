"""Compare current PostgreSQL chapter identity/provenance/text hashes with completed exports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from historysys.db import connect

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    expected={}
    errors=[]
    paragraph_count=0
    characters=0
    for path in sorted(args.folder.glob('*.jsonl')):
        if path.name.endswith('.part.jsonl'):
            continue
        with path.open(encoding='utf-8-sig') as stream:
            for line in stream:
                if not line.strip():continue
                r=json.loads(line)
                cid=r['chapter_id']
                if cid in expected:
                    errors.append({'chapter_id':cid,'error':'duplicate source chapter'})
                text=r['text']
                expected[cid]={k:r[k] for k in ('book_id','chapter_index','source_sha256','decoder','verification_status')}
                expected[cid].update(title=r['chapter_title'],text_md5=hashlib.md5(text.encode('utf-8')).hexdigest() if text is not None else None,
                                     paragraph_count=len(r['paragraphs']))
                paragraph_count+=len(r['paragraphs'])
                characters+=len(text) if text is not None else 0
    checked=0
    with connect() as conn:
        conn.execute('SET statement_timeout=0')
        with conn.cursor(name='audit_chapters') as cursor:
            cursor.itersize=500
            cursor.execute('''SELECT c.chapter_id,c.book_id,c.chapter_index,c.title,c.source_sha256,c.decoder,
                c.verification_status,md5(c.original_text) AS text_md5,
                (SELECT count(*) FROM history.paragraphs p WHERE p.chapter_id=c.chapter_id) AS paragraph_count
                FROM history.chapters c ORDER BY c.chapter_id''')
            for row in cursor:
                cid=row.pop('chapter_id')
                source=expected.pop(cid,None)
                if source is None:
                    errors.append({'chapter_id':cid,'error':'unexpected database chapter'})
                else:
                    different=[key for key in source if row.get(key)!=source[key]]
                    if different:
                        errors.append({'chapter_id':cid,'mismatched_fields':different})
                checked+=1
        errors.extend({'chapter_id':cid,'error':'missing database chapter'} for cid in expected)
        totals=conn.execute('''SELECT (SELECT count(*) FROM history.books) AS books,count(*) AS chapters,
            count(original_text) AS text_chapters,sum(length(original_text))::bigint AS characters,
            (SELECT count(*) FROM history.paragraphs) AS paragraphs FROM history.chapters''').fetchone()
    report={'checked_chapters':checked,'expected_characters':characters,'expected_paragraphs':paragraph_count,
            'database_totals':totals,'error_count':len(errors),'errors':errors[:100],
            'scope':'All chapter original UTF8 text MD5, identity, title, source SHA256, decoder, verification status and per-chapter paragraph counts; not historical collation or layout audit.'}
    target=Path(__file__).resolve().parent/'.local'/'database-audit-latest.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if errors:sys.exit(1)

if __name__=='__main__':main()
