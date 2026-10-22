"""Import complete JSONL exports, one atomic transaction per book, resumable by hash."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from historysys.db import connect,migrate
from historysys.importer import import_jsonl

def already_current(digest):
    # Historical success alone is insufficient: another export may have overwritten the chapters.
    with connect() as conn:
        row=conn.execute('''SELECT r.record_count = (
            SELECT count(*) FROM history.chapters c JOIN history.import_runs active ON active.id=c.import_run_id
            WHERE active.input_sha256=%s AND active.status='succeeded') AS current_match
            FROM history.import_runs r WHERE r.input_sha256=%s AND r.status='succeeded'
            ORDER BY r.id DESC LIMIT 1''',(digest,digest)).fetchone()
    return bool(row and row['current_match'])

def rebuild_indexes():
    # Fixed application-owned indexes only; never derive SQL identifiers from input files.
    for name,column in [('paragraphs_original_trgm','original_text'),('paragraphs_normalized_trgm','normalized_text')]:
        print(json.dumps({'phase':'index_build_start','index':name}),flush=True)
        started=time.monotonic()
        with connect() as conn:
            conn.execute('SET statement_timeout=0')
            conn.execute("SET maintenance_work_mem='256MB'")
            conn.execute(f'CREATE INDEX IF NOT EXISTS {name} ON history.paragraphs USING gin({column} gin_trgm_ops)')
        print(json.dumps({'phase':'index_build_done','index':name,'seconds':round(time.monotonic()-started,2)}),flush=True)
    with connect() as conn:
        conn.execute('SET statement_timeout=0')
        conn.execute('ANALYZE history.paragraphs')
        conn.execute('ANALYZE history.chapters')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--force',action='store_true',help='Reimport even when same input hash already succeeded')
    parser.add_argument('--bulk-index-build',action='store_true',help='Private initial import: rebuild owned GIN indexes once at end, including on failure')
    args=parser.parse_args()
    if args.bulk_index_build:
        from launch_service import ensure_cluster
        ensure_cluster()
    else:
        migrate()
    files=sorted(p for p in args.folder.glob('*.jsonl') if not p.name.endswith('.part.jsonl'))
    if not files:
        raise SystemExit('No completed .jsonl files found')
    started=time.monotonic()
    results=[]
    try:
        if args.bulk_index_build:
            with connect() as conn:
                conn.execute('DROP INDEX IF EXISTS history.paragraphs_original_trgm')
                conn.execute('DROP INDEX IF EXISTS history.paragraphs_normalized_trgm')
            print(json.dumps({'phase':'import_start','files':len(files),'deferred_gin':True}),flush=True)
        for index,path in enumerate(files,1):
            with path.open('rb') as stream:
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if not args.force and already_current(digest):
                results.append({'file':path.name,'status':'unchanged'})
            else:
                try:
                    result=import_jsonl(path)
                    results.append({'file':path.name,'status':'imported',**result})
                except Exception as exc:
                    results.append({'file':path.name,'status':'failed','error_type':type(exc).__name__})
            if index%25==0 or index==len(files):
                print(json.dumps({'phase':'import_progress','processed':index,'files':len(files),
                                  'seconds':round(time.monotonic()-started,2)}),flush=True)
    finally:
        if args.bulk_index_build:
            rebuild_indexes()
    with connect() as conn:
        totals=conn.execute('''SELECT (SELECT count(*) FROM history.books) AS books,count(*) AS chapters,
            count(original_text) AS text_chapters,coalesce(sum(length(original_text)),0)::bigint AS characters,
            (SELECT count(*) FROM history.paragraphs) AS paragraphs FROM history.chapters''').fetchone()
    report={'files':len(files),'imported':sum(r['status']=='imported' for r in results),
            'unchanged':sum(r['status']=='unchanged' for r in results),
            'failed':sum(r['status']=='failed' for r in results),'seconds':round(time.monotonic()-started,2),
            'database_totals':totals,'results':results}
    target=Path(__file__).resolve().parent/'.local'/'folder-import-report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False),flush=True)
    if report['failed']:
        sys.exit(1)

if __name__=='__main__':main()
