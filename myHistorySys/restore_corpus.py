"""Explicit restoration import into the configured existing database.

Validates every export hash and DB paragraph before writing evidence/assets.
All writes are one transaction; source chapters and paragraphs are untouched.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from psycopg.types.json import Jsonb
from historysys.db import connect

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from readerTool.character_reading import reading_view
from readerTool.rtf_assets import extract_assets


def sha(data):
    return hashlib.sha256(data).hexdigest()


def paragraph_digest(paragraphs):
    h = hashlib.sha256()
    for ordinal, original, normalized in paragraphs:
        h.update(json.dumps([ordinal, original, normalized], ensure_ascii=False,
                            separators=(',', ':')).encode('utf8'))
        h.update(b'\n')
    return h.hexdigest()


def restore(folder, notes_path, write=False):
    import unicodedata
    notes_bytes = notes_path.read_bytes()
    notes = json.loads(notes_bytes)
    expected = {}
    asset_rows = []
    control_counts = Counter()
    for path in sorted(folder.glob('*.jsonl')):
        if path.name.endswith('.part.jsonl'): continue
        with path.open('rb') as stream:
            export_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        book_report = json.loads(path.with_suffix('.report.json').read_text(encoding='utf8'))
        if export_sha != book_report['output_sha256']:
            raise ValueError('Export hash mismatch: '+path.stem)
        if notes['source_exports_sha256'].get(path.name) != export_sha:
            raise ValueError('Character inventory based on a different export: '+path.stem)
        for line in path.open(encoding='utf8'):
            row = json.loads(line)
            cid = row['chapter_id']
            if cid in expected: raise ValueError('Duplicate chapter: '+cid)
            expected[cid] = {
                'source_sha256': row['source_sha256'], 'decoder': row['decoder'],
                'text_sha256': sha(row['text'].encode('utf8')) if row['text'] is not None else None,
                'paragraph_digest': paragraph_digest((p['ordinal'], p['text'], unicodedata.normalize('NFKC', p['text'])) for p in row['paragraphs']),
                'paragraphs': len(row['paragraphs']),
                'raw_sha256': row['metadata']['raw_sha256'],
                'assets': row['metadata'].get('embedded_object_count', 0)}
            control_counts.update(f'U+{ord(c):04X}' for c in (row['text'] or '')
                                  if ord(c)<32 and c not in '\r\n\t' or ord(c)==127)
            if expected[cid]['assets']:
                name = row['metadata']['raw_file']
                if Path(name).name != name: raise ValueError('Unsafe raw filename')
                raw = (folder.parent/'raw'/row['book_id']/name).read_bytes()
                if sha(raw) != expected[cid]['raw_sha256']: raise ValueError('RTF hash mismatch: '+cid)
                assets = extract_assets(raw)
                if len(assets) != expected[cid]['assets']: raise ValueError('Asset coverage mismatch: '+cid)
                asset_rows.extend((cid, a) for a in assets)
    print(json.dumps({'phase':'exports_validated','chapters':len(expected),
                      'assets':len(asset_rows)}),flush=True)
    report = {'mode': 'import' if write else 'check', 'chapters_checked': 0,
              'paragraphs_checked': 0, 'character_chapters': 0, 'character_occurrences': 0,
              'replacements': 0, 'unresolved': 0, 'assets': len(asset_rows),
              'asset_chapters': len({cid for cid, _ in asset_rows}),
              'picture_payloads': sum(a['payload'] is not None for _, a in asset_rows),
              'control_counts': dict(control_counts), 'notes_sha256': sha(notes_bytes),
              'original_text_rewritten': False, 'historical_status_upgraded': False}
    with connect() as conn:
        conn.execute('SET statement_timeout=0')
        # A consistent snapshot and shared locks prevent chapter reimport during verification/import.
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        conn.execute('LOCK TABLE history.chapters, history.paragraphs IN SHARE MODE')
        identity = conn.execute('SELECT current_database() AS database, inet_server_port() AS port').fetchone()
        report['target'] = identity
        seen = set()
        with conn.cursor(name='restore_chapters') as cursor:
            cursor.execute('SELECT chapter_id,original_text,source_sha256,decoder,verification_status,metadata FROM history.chapters ORDER BY chapter_id')
            character_rows = []
            for row in cursor:
                cid = row['chapter_id']; seen.add(cid)
                e = expected.get(cid)
                if not e: raise ValueError('Unexpected DB chapter: '+cid)
                digest = sha(row['original_text'].encode('utf8')) if row['original_text'] is not None else None
                if (digest != e['text_sha256'] or row['source_sha256'] != e['source_sha256'] or
                    row['decoder'] != e['decoder'] or row['metadata'].get('raw_sha256') != e['raw_sha256']):
                    raise ValueError('Database provenance mismatch: '+cid)
                if cid in notes['chapters']:
                    record = notes['chapters'][cid]
                    view = reading_view(row, record)
                    character_rows.append((cid, row['source_sha256'], row['decoder'], digest,
                        view['mapping_version'], Jsonb(record), view['reading_text'],
                        view['replacements_applied'], view['unresolved_occurrences']))
                    report['character_chapters'] += 1
                    report['character_occurrences'] += len(view['notes'])
                    report['replacements'] += view['replacements_applied']
                    report['unresolved'] += view['unresolved_occurrences']
                report['chapters_checked'] += 1
        if seen != set(expected) or set(notes['chapters'])-seen:
            raise ValueError('Missing chapters in database or character notes')
        # Stream full paragraph text (including normalized strings) chapter by chapter.
        current = None; group = [] ; paragraph_seen = set()
        def check_group(cid, values):
            if cid is None: return
            if paragraph_digest(values) != expected[cid]['paragraph_digest'] or len(values) != expected[cid]['paragraphs']:
                raise ValueError('Paragraph content/order mismatch: '+cid)
            paragraph_seen.add(cid)
        with conn.cursor(name='restore_paragraphs') as cursor:
            cursor.itersize = 2000
            cursor.execute('SELECT chapter_id,ordinal,original_text,normalized_text FROM history.paragraphs ORDER BY chapter_id,ordinal')
            for p in cursor:
                if p['chapter_id'] != current:
                    check_group(current, group); current = p['chapter_id']; group = []
                if current not in expected: raise ValueError('Unexpected paragraph chapter')
                group.append((p['ordinal'],p['original_text'],p['normalized_text']))
                report['paragraphs_checked'] += 1
                if report['paragraphs_checked'] % 250000 == 0:
                    print(json.dumps({'phase':'paragraph_content_audit',
                                      'checked':report['paragraphs_checked']}),flush=True)
            check_group(current, group)
        if any(e['paragraphs'] for cid,e in expected.items() if cid not in paragraph_seen):
            raise ValueError('Missing database paragraphs')
        if sha(notes_path.read_bytes()) != report['notes_sha256']:
            raise ValueError('Character notes changed during validation')
        if write:
            conn.execute((Path(__file__).parent/'migrations/002_restoration.sql').read_text(encoding='utf8'))
            # Exact corpus snapshot: replace evidence in the same transaction, idempotently.
            conn.execute('DELETE FROM history.character_notes')
            conn.execute('DELETE FROM history.chapter_assets')
            with conn.cursor() as cursor:
                cursor.executemany('''INSERT INTO history.character_notes
                    (chapter_id,source_sha256,decoder,text_sha256,mapping_version,record,reading_text,replacements,unresolved)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''', character_rows)
                cursor.executemany('''INSERT INTO history.chapter_assets
                    (chapter_id,ordinal,kind,source_sha256,decoder,raw_rtf_sha256,start_byte,end_byte,parent_ordinal,
                    format,status,raw_group_sha256,raw_group,payload_sha256,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    [(cid,a['ordinal'],a['kind'],expected[cid]['source_sha256'],expected[cid]['decoder'],
                      expected[cid]['raw_sha256'],a['start'],a['end'],a['parent_ordinal'],a['format'],
                      a['status'],a['raw_group_sha256'],a['raw_group'],a['payload_sha256'],a['payload'])
                     for cid,a in asset_rows])
            # Read back each stored binary, not merely a successful INSERT count.
            for row in conn.execute('SELECT raw_group,raw_group_sha256,payload,payload_sha256 FROM history.chapter_assets'):
                if sha(bytes(row['raw_group'])) != row['raw_group_sha256'] or (row['payload'] is not None and sha(bytes(row['payload'])) != row['payload_sha256']):
                    raise ValueError('Database asset readback mismatch')
            for row in conn.execute('SELECT * FROM history.character_notes'):
                original = notes['chapters'][row['chapter_id']]
                if row['record'] != original: raise ValueError('Database character readback mismatch')
                chapter = conn.execute('SELECT chapter_id,original_text,source_sha256,decoder FROM history.chapters WHERE chapter_id=%s',
                                       (row['chapter_id'],)).fetchone()
                view = reading_view(chapter, original)
                if (view['reading_text']!=row['reading_text'] or view['replacements_applied']!=row['replacements']
                    or view['unresolved_occurrences']!=row['unresolved']):
                    raise ValueError('Database reading text readback mismatch')
    report['committed'] = write
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Explicitly create restoration tables and import evidence')
    args = parser.parse_args()
    report = restore(PROJECT/'readerTool/.local/exports', PROJECT/'readerTool/.local/unknowns/chapter-notes.json', args.write)
    dest = Path(__file__).parent/'.local/restoration-audit-latest.json'
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=True),flush=True)

if __name__ == '__main__': main()
