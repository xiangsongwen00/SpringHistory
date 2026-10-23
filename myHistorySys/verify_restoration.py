"""Read-only API verification using the real configured database, no listener.

Requires requirements-dev.txt for FastAPI TestClient. Never creates test rows.
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from historysys.api import app
from historysys.db import connect


def main():
    with TestClient(app) as client:
        response = client.get('/restoration')
        response.raise_for_status()
        summary = response.json()
        assert summary['available'] and summary['stale_character_chapters'] == 0 and summary['stale_assets'] == 0
        with connect() as conn:
            notes = conn.execute('SELECT chapter_id,reading_text,replacements,unresolved FROM history.character_notes ORDER BY chapter_id').fetchall()
            resources = conn.execute('SELECT chapter_id,ordinal,raw_group_sha256,payload_sha256 FROM history.chapter_assets ORDER BY chapter_id,ordinal').fetchall()
        # Prove the database path works independently of the local notes JSON.
        with patch('historysys.characters.NOTES', Path('.local/nonexistent-report-do-not-create')):
            for row in notes:
                response = client.get('/chapters/'+row['chapter_id']+'/characters')
                response.raise_for_status()
                data = response.json()
                assert data['character_record_storage'] == 'postgresql'
                assert data['reading_text'] == row['reading_text']
                assert data['replacements_applied'] == row['replacements']
                assert data['unresolved_occurrences'] == row['unresolved']
        for row in resources:
            for part, digest in [('raw',row['raw_group_sha256']),('payload',row['payload_sha256'])]:
                response = client.get('/chapters/'+row['chapter_id']+'/assets/'+str(row['ordinal'])+'/download',params={'part':part})
                if digest is None:
                    assert response.status_code == 404
                else:
                    response.raise_for_status()
                    assert hashlib.sha256(response.content).hexdigest() == digest
        for book in ('B01-137','B01-138','B02-163'):
            response = client.get('/search',params={'book_id':book,'q':'天下','limit':2})
            response.raise_for_status()
            assert response.json()['items'], book
        assert client.get('/chapters/DOES_NOT_EXIST/assets').status_code == 404
    result = {'restoration':summary,'character_endpoints_checked':len(notes),
              'assets_checked':len(resources),
              'downloads_checked':sum(1+bool(r['payload_sha256']) for r in resources),
              'focus_book_searches':3,'local_notes_file_disabled_for_test':True,
              'method':'In-process FastAPI TestClient against existing PostgreSQL; no API listener started.'}
    Path(__file__).with_name('.local').joinpath('restoration-api-check.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
