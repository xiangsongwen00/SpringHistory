"""Read-only localhost API: no arbitrary SQL, filenames or import endpoints."""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import psycopg
from .db import connect
from .importer import normalize

app=FastAPI(title='SpringHistory text service',version='0.1.0')
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.exception_handler(psycopg.Error)
async def database_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503,content={'detail':'Database unavailable or query failed; inspect local database logs.'})

@app.get('/health')
def health():
    try:
        with connect() as conn:
            state=conn.execute('''SELECT count(*) AS chapters,
                count(*) FILTER(WHERE original_text IS NOT NULL) AS text_chapters,
                count(*) FILTER(WHERE verification_status='verified_sample') AS sample_verified_chapters
                FROM history.chapters''').fetchone()
            version=conn.execute('SHOW server_version').fetchone()['server_version']
        return {'status':'ok','database':'connected','postgres_version':version,**state}
    except (psycopg.Error,RuntimeError):
        raise HTTPException(503,'Database unavailable or schema missing')

@app.get('/books')
def books(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0,le=1000000)):
    with connect() as conn:
        return conn.execute('''SELECT b.book_id,b.title,count(c.chapter_id) AS chapter_count,
            count(c.original_text) AS text_chapter_count FROM history.books b
            LEFT JOIN history.chapters c USING(book_id) GROUP BY b.book_id ORDER BY b.book_id LIMIT %s OFFSET %s''',(limit,offset)).fetchall()

@app.get('/books/{book_id}/chapters')
def chapters(book_id:str,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0,le=1000000)):
    with connect() as conn:
        return conn.execute('''SELECT chapter_id,book_id,chapter_index,title,
            CASE WHEN btrim(title)='' THEN '原记录无标题' ELSE title END AS display_title,verification_status,
            source_sha256,decoder,length(original_text) AS text_length
            FROM history.chapters WHERE book_id=%s ORDER BY chapter_index LIMIT %s OFFSET %s''',(book_id,limit,offset)).fetchall()

@app.get('/chapters/{chapter_id}')
def chapter(chapter_id:str):
    with connect() as conn:
        row=conn.execute('''SELECT c.*,b.title AS book_title FROM history.chapters c
            JOIN history.books b USING(book_id) WHERE c.chapter_id=%s''',(chapter_id,)).fetchone()
        if row is None:
            raise HTTPException(404,'Chapter not found')
        row['display_title']=row['title'] if row['title'].strip() else '原记录无标题'
        return row

@app.get('/chapters/{chapter_id}/paragraphs')
def paragraphs(chapter_id:str,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0,le=1000000)):
    with connect() as conn:
        return conn.execute('''SELECT p.chapter_id,p.ordinal,p.original_text,p.normalized_text,
            c.verification_status,c.decoder,c.source_sha256 FROM history.paragraphs p
            JOIN history.chapters c USING(chapter_id) WHERE p.chapter_id=%s ORDER BY p.ordinal LIMIT %s OFFSET %s''',
            (chapter_id,limit,offset)).fetchall()

def escape_like(value):
    return value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')

@app.get('/search')
def search(q:str=Query(min_length=1,max_length=200),book_id:str|None=None,
           limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=100000),normalized:bool=False):
    if '\x00' in q or not q.strip():
        raise HTTPException(422,'Query must be nonblank and NUL-free')
    term=normalize(q) if normalized else q
    # Only constant server-selected column fragments; all user values are parameters.
    col='p.normalized_text' if normalized else 'p.original_text'
    condition=f"{col} LIKE %s ESCAPE E'\\\\'"
    params=['%'+escape_like(term)+'%']
    if book_id is not None:
        condition+=' AND c.book_id=%s'
        params.append(book_id)
    with connect() as conn:
        rows=conn.execute(f'''SELECT c.book_id,b.title AS book_title,c.chapter_id,c.title AS chapter_title,
            p.ordinal,p.original_text,p.normalized_text,c.verification_status,c.source_file,c.source_sha256,c.decoder
            FROM history.paragraphs p JOIN history.chapters c USING(chapter_id)
            JOIN history.books b USING(book_id) WHERE {condition}
            ORDER BY c.book_id,c.chapter_index,p.ordinal LIMIT %s OFFSET %s''',tuple(params+[limit+1,offset])).fetchall()
    has_more=len(rows)>limit
    items=rows[:limit]
    for row in items:
        row['display_title']=row['chapter_title'] if row['chapter_title'].strip() else '原记录无标题'
        matched=row['normalized_text'] if normalized else row['original_text']
        positions=[]
        start=0
        while True:
            pos=matched.find(term,start)
            if pos<0:
                break
            positions.append(pos)
            start=pos+1
        row['match_offsets']=positions
        row['offset_basis']='normalized_unicode_codepoints' if normalized else 'original_unicode_codepoints'
    return {'query':q,'mode':'normalized_literal_phrase' if normalized else 'original_literal_phrase',
            'strategy':'short_literal_scan' if len(term)<3 else 'trigram_eligible_literal',
            'scope_note':'matches occur within one paragraph; punctuation/whitespace preserved',
            'items':items,'limit':limit,'offset':offset,'has_more':has_more}
