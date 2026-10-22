"""Atomic streaming JSONL import. Failed imports preserve previous library state."""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from psycopg.types.json import Jsonb
from .db import connect, migrate

STATUSES = {'decoded_unverified','verified_sample','metadata_only'}

def normalize(text):
    # Search-only copy; never replace original quotation text.
    return unicodedata.normalize('NFKC', text)

def validate(r):
    if not isinstance(r, dict) or type(r.get('schema_version')) is not int or r.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    for key in ('book_id','book_title','chapter_id','source_file','decoder'):
        if not isinstance(r.get(key), str) or not r[key].strip() or '\x00' in r[key]:
            raise ValueError(f'{key}: nonempty string required')
    if not isinstance(r.get('chapter_title'),str) or '\x00' in r['chapter_title']:
        raise ValueError('chapter_title must be a NUL-free string; source blank titles are preserved')
    i = r.get('chapter_index')
    if type(i) is not int or i < 0 or r['chapter_id'] != f"{r['book_id']}:{i}":
        raise ValueError('chapter_index/id mismatch')
    if not re.fullmatch('[a-f0-9]{64}', r.get('source_sha256','')):
        raise ValueError('source_sha256 must be lowercase sha256')
    status = r.get('verification_status')
    if status not in STATUSES:
        raise ValueError('invalid verification_status')
    text, paragraphs = r.get('text'), r.get('paragraphs')
    if not isinstance(paragraphs,list) or not isinstance(r.get('metadata'),dict):
        raise ValueError('paragraphs list and metadata object required')
    if status == 'metadata_only':
        if text is not None or paragraphs:
            raise ValueError('metadata_only must not contain body or paragraphs')
    else:
        if not isinstance(text,str) or not text.strip() or '\x00' in text:
            raise ValueError('decoded records require nonempty NUL-free text')
        if not paragraphs:
            raise ValueError('decoded records require paragraphs')
    previous = -1
    cursor = 0
    for p in paragraphs:
        if not isinstance(p,dict) or type(p.get('ordinal')) is not int or p['ordinal'] <= previous:
            raise ValueError('paragraph ordinals must be nonnegative and strictly increasing')
        s = p.get('text')
        if not isinstance(s,str) or not s.strip() or '\x00' in s:
            raise ValueError('invalid paragraph text')
        pos = text.find(s,cursor)
        if pos < 0:
            raise ValueError('paragraph must occur in original text in order')
        cursor = pos + len(s)
        previous = p['ordinal']
    # All non-whitespace body content must be represented for paragraph search.
    if status != 'metadata_only' and ''.join(text.split()) != ''.join(''.join(p['text'].split()) for p in paragraphs):
        raise ValueError('paragraphs must cover all body content')
    return r

def import_jsonl(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            h.update(chunk)
    digest = h.hexdigest()
    with connect() as conn:
        run_id = conn.execute('INSERT INTO history.import_runs(input_file,input_sha256,status) VALUES(%s,%s,%s) RETURNING id',
                              (str(path),digest,'running')).fetchone()['id']
    count = 0
    try:
        with connect() as conn:
            # One writer, atomic complete input. API readers retain previous committed snapshot.
            conn.execute("SELECT pg_advisory_xact_lock(184683101)")
            seen = set()
            imported_hash=hashlib.sha256()
            with path.open('rb') as stream:
                for line_num,raw_line in enumerate(stream,1):
                    imported_hash.update(raw_line)
                    line=raw_line.decode('utf-8-sig' if line_num==1 else 'utf-8')
                    if not line.strip():
                        continue
                    try:
                        r = validate(json.loads(line))
                    except (ValueError,TypeError) as exc:
                        raise ValueError(f'line {line_num}: {exc}') from exc
                    if r['chapter_id'] in seen:
                        raise ValueError(f'line {line_num}: duplicate chapter_id')
                    seen.add(r['chapter_id'])
                    conn.execute('INSERT INTO history.books(book_id,title) VALUES(%s,%s) ON CONFLICT(book_id) DO UPDATE SET title=excluded.title,updated_at=now()',
                                 (r['book_id'],r['book_title']))
                    conn.execute('''INSERT INTO history.chapters(chapter_id,book_id,chapter_index,title,source_file,source_sha256,decoder,verification_status,original_text,normalized_text,metadata,import_run_id)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(chapter_id) DO UPDATE SET title=excluded.title,source_file=excluded.source_file,
                        source_sha256=excluded.source_sha256,decoder=excluded.decoder,verification_status=excluded.verification_status,
                        original_text=excluded.original_text,normalized_text=excluded.normalized_text,metadata=excluded.metadata,
                        import_run_id=excluded.import_run_id,updated_at=now()''',
                        (r['chapter_id'],r['book_id'],r['chapter_index'],r['chapter_title'],r['source_file'],r['source_sha256'],
                         r['decoder'],r['verification_status'],r['text'],normalize(r['text']) if r['text'] is not None else None,Jsonb(r['metadata']),run_id))
                    conn.execute('DELETE FROM history.paragraphs WHERE chapter_id=%s',(r['chapter_id'],))
                    if r['paragraphs']:
                        with conn.cursor() as cur:
                            with cur.copy('COPY history.paragraphs(chapter_id,ordinal,original_text,normalized_text) FROM STDIN') as copy:
                                for p in r['paragraphs']:
                                    copy.write_row((r['chapter_id'],p['ordinal'],p['text'],normalize(p['text'])))
                    count += 1
            if imported_hash.hexdigest()!=digest:
                raise ValueError('Input file changed during import; transaction rolled back, retry completed export')
            conn.execute("UPDATE history.import_runs SET status='succeeded',record_count=%s,completed_at=now() WHERE id=%s",(count,run_id))
    except BaseException as exc:
        with connect() as conn:
            # Avoid putting raw input, database connection details or credentials in audit errors.
            conn.execute("UPDATE history.import_runs SET status='failed',error=%s,completed_at=now() WHERE id=%s",(type(exc).__name__,run_id))
        raise
    return {'run_id':run_id,'record_count':count,'input_sha256':digest}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('jsonl',nargs='?')
    parser.add_argument('--migrate',action='store_true')
    args=parser.parse_args()
    if args.migrate:
        migrate()
    if args.jsonl:
        print(json.dumps(import_jsonl(args.jsonl),ensure_ascii=False))

if __name__=='__main__':
    main()
