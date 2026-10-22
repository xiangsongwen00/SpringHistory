"""Read-only extraction -> archival RTF -> strict Unicode -> versioned JSONL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'reader'))
from hanji_catalog import scan_catalog
from rtf_text import decode_rtf

DECODER='ftr-dll32-rtf-v2'

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def export_book(root, book, python32, output, timeout=120, resume=False):
    source=Path(book['project']).with_suffix('.AMG')
    source_hash=sha256(source)
    dll_hash=sha256(root/'Ftrquery.dll')
    final=output/(book['id']+'.jsonl')
    report=output/(book['id']+'.report.json')
    if resume and final.exists() and report.exists():
        old=json.loads(report.read_text(encoding='utf-8'))
        if (old.get('source_sha256')==source_hash and old.get('decoder')==DECODER
                and old.get('dll_sha256')==dll_hash and old.get('failures')==0):
            if old.get('output_sha256')==sha256(final): return dict(old,resumed=True)
    raw_dir=output.parent/'raw'/book['id']
    command=[str(python32),str(HERE/'native_worker32.py'),'--root',str(root),
             '--book',book['id'],'--output',str(raw_dir)]
    completed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',
        timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if completed.returncode:
        raise RuntimeError(f'Native worker failed: {completed.returncode}: {completed.stderr[-1500:]}')
    manifest=[json.loads(line) for line in (raw_dir/'manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    summary={'book_id':book['id'],'book_title':book['title'],'source_sha256':source_hash,
             'dll_sha256':dll_hash,
             'decoder':DECODER,'chapters':len(manifest),'decoded':0,'failures':0,'characters':0,
             'paragraphs':0,'embedded_objects':0,'private_use_characters':0,
             'gb18030_extensions':0,'errors':[]}
    part=final.with_suffix('.part.jsonl')
    with part.open('w',encoding='utf-8',newline='\n') as stream:
        for chapter in manifest:
            row={'schema_version':1,'book_id':book['id'],'book_title':book['title'],
                 'chapter_id':f"{book['id']}:{chapter['chapter_index']}",
                 'chapter_index':chapter['chapter_index'],'chapter_title':chapter['chapter_title'],
                 'source_file':str(source),'source_sha256':source_hash,'decoder':DECODER,
                 'verification_status':'metadata_only','text':None,'paragraphs':[],
                 'metadata':dict(chapter)}
            row['metadata']['dll_sha256']=dll_hash
            try:
                raw=(raw_dir/chapter['raw_file']).read_bytes()
                if sha256(raw_dir/chapter['raw_file'])!=chapter['raw_sha256']: raise ValueError('Raw hash mismatch')
                text,metadata=decode_rtf(raw)
                if not text.strip(): raise ValueError('Empty decoded text')
                paragraphs=[{'ordinal':i,'text':line} for i,line in enumerate(text.splitlines()) if line.strip()]
                row.update(text=text,paragraphs=paragraphs,verification_status='decoded_unverified')
                row['metadata'].update(metadata)
                summary['decoded']+=1;summary['characters']+=len(text)
                summary['paragraphs']+=len(paragraphs)
                summary['embedded_objects']+=metadata['embedded_object_count']
                summary['private_use_characters']+=metadata['private_use_count']
                summary['gb18030_extensions']+=metadata['gb18030_extension_count']
            except Exception as error:
                row['metadata']['failure']=str(error)
                summary['failures']+=1
                summary['errors'].append({'chapter_index':chapter['chapter_index'],'error':str(error)})
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    if sha256(source)!=source_hash: raise RuntimeError('Source changed during extraction; output not committed')
    part.replace(final)
    summary['output_sha256']=sha256(final)
    report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(os.environ.get('HANJI_ROOT','E:/汉籍全文检索系统')))
    parser.add_argument('--book',action='append')
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--python32',type=Path,default=HERE/'.local/python32/python.exe')
    parser.add_argument('--output',type=Path,default=HERE/'.local/exports')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--timeout',type=int,default=120)
    parser.add_argument('--workers',type=int,default=1,help='Independent book processes (1-8)')
    args=parser.parse_args()
    args.root=args.root.resolve(); args.output=args.output.resolve()
    if args.output==args.root or args.root in args.output.parents:
        parser.error('Output must be outside source library')
    if bool(args.all)==bool(args.book): parser.error('Choose --all or one/more --book')
    if not 1 <= args.workers <= 8: parser.error('--workers must be 1-8')
    if not (args.root/'lib').is_dir() or not (args.root/'Ftrquery.dll').is_file():
        parser.error('Source library lib/ or Ftrquery.dll not found')
    if not args.python32.is_file(): parser.error('x86 runtime missing; run setup_runtime.py first')
    books=scan_catalog(args.root)
    if not books: parser.error('No supported book catalogues found')
    if args.book:
        requested=set(args.book);books=[b for b in books if b['id'] in requested]
        if {b['id'] for b in books}!=requested: parser.error('Unknown book ID')
    args.output.mkdir(parents=True,exist_ok=True)
    summary={'decoder':DECODER,'books':len(books),'succeeded':0,'failed':0,'decoded_chapters':0,
             'failed_chapters':0,'characters':0,'results':[]}
    started=time.monotonic()
    pool=None
    jobs=((book,None) for book in books)
    if args.workers > 1:
        pool=ProcessPoolExecutor(max_workers=args.workers)
        futures={pool.submit(export_book,args.root,book,args.python32,args.output,
                             args.timeout,args.resume):book for book in books}
        jobs=((futures[future],future) for future in as_completed(futures))
    for book,future in jobs:
        try:
            result=(future.result() if future is not None else
                    export_book(args.root,book,args.python32,args.output,args.timeout,args.resume))
            summary['succeeded']+=1;summary['decoded_chapters']+=result['decoded']
            summary['failed_chapters']+=result['failures'];summary['characters']+=result['characters']
            print(json.dumps({k:v for k,v in result.items() if k!='errors'},ensure_ascii=True),flush=True)
        except Exception as error:
            result={'book_id':book['id'],'error':str(error)}
            summary['failed']+=1
            print(json.dumps(result,ensure_ascii=True),flush=True)
        summary['results'].append(result)
        summary['elapsed_seconds']=round(time.monotonic()-started,2)
        (args.output/'run-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if pool is not None: pool.shutdown()
    return 1 if summary['failed'] or summary['failed_chapters'] else 0

if __name__=='__main__': sys.exit(main())
