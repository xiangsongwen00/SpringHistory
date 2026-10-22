"""Verify completed exports and provenance, without changing corpus or verification state."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def audit(folder, check_source=False, check_raw=False):
    totals=dict(books=0,chapters=0,text_chapters=0,characters=0,paragraphs=0,
                metadata_only=0,private_use_characters=0,embedded_objects=0)
    errors=[]
    for path in sorted(folder.glob('*.jsonl')):
        if path.name.endswith('.part.jsonl'): continue
        try:
            book_totals={key:0 for key in totals}
            report=json.loads(path.with_suffix('.report.json').read_text(encoding='utf-8'))
            if digest(path)!=report['output_sha256']: raise ValueError('Output hash mismatch')
            count=characters=0
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    if row['chapter_index']!=count or row['chapter_id']!=f'{path.stem}:{count}':
                        raise ValueError('Chapter identity/order mismatch')
                    if row['source_sha256']!=report['source_sha256'] or row['decoder']!=report['decoder']:
                        raise ValueError('Source/version mismatch')
                    if row['metadata']['dll_sha256']!=report['dll_sha256']:
                        raise ValueError('DLL provenance mismatch')
                    if check_raw:
                        name=row['metadata']['raw_file']
                        if Path(name).name!=name: raise ValueError('Invalid raw archive filename')
                        raw=folder.parent/'raw'/path.stem/name
                        if raw.stat().st_size!=row['metadata']['raw_size'] or digest(raw)!=row['metadata']['raw_sha256']:
                            raise ValueError('Raw RTF archive mismatch')
                    if check_source and count==0 and digest(row['source_file'])!=report['source_sha256']:
                        raise ValueError('Current source hash differs')
                    count+=1
                    if row['verification_status']=='metadata_only':
                        if row['text'] is not None or row['paragraphs']: raise ValueError('False decoded content')
                        book_totals['metadata_only']+=1
                        continue
                    text=row['text']
                    if not text.strip() or '\ufffd' in text or '\x00' in text:
                        raise ValueError('Empty/lossy/NUL text')
                    expected=[{'ordinal':i,'text':s} for i,s in enumerate(text.splitlines()) if s.strip()]
                    if row['paragraphs']!=expected: raise ValueError('Paragraph coverage mismatch')
                    characters+=len(text); book_totals['text_chapters']+=1
                    book_totals['paragraphs']+=len(expected)
                    book_totals['private_use_characters']+=row['metadata']['private_use_count']
                    book_totals['embedded_objects']+=row['metadata']['embedded_object_count']
            if count!=report['chapters'] or characters!=report['characters']:
                raise ValueError('Report count mismatch')
            book_totals.update(books=1,chapters=count,characters=characters)
            for key,value in book_totals.items(): totals[key]+=value
        except Exception as exc:
            errors.append({'book_id':path.stem,'error':str(exc)})
    return {'totals':totals,'source_hashes_checked':check_source,
            'raw_hashes_checked':check_raw,'errors':errors}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',nargs='?',type=Path,default=Path(__file__).resolve().parent/'.local/exports')
    parser.add_argument('--check-source',action='store_true')
    parser.add_argument('--check-raw',action='store_true')
    args=parser.parse_args()
    result=audit(args.folder,args.check_source,args.check_raw)
    (args.folder/'audit-latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return 1 if result['errors'] or not result['totals']['books'] else 0

if __name__=='__main__': raise SystemExit(main())
