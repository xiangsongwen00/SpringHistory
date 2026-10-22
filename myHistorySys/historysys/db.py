import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]

def database_url():
    value = os.environ.get('HISTORY_DATABASE_URL')
    if value:
        return value
    local = ROOT / '.local' / 'database.url'
    if local.exists():
        return local.read_text(encoding='utf-8').strip()
    raise RuntimeError('Set HISTORY_DATABASE_URL or run init_local.py')

def connect():
    return psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=3,
                           options='-c statement_timeout=15000')

def migrate():
    with connect() as conn:
        # Explicit DDL maintenance may rebuild a full-corpus index; API queries keep their 15s bound.
        conn.execute('SET statement_timeout=0')
        conn.execute((ROOT/'migrations'/'001_initial.sql').read_text(encoding='utf-8'))
        if not conn.execute('SELECT show_trgm(%s) AS t',('五年内不加税赋',)).fetchone()['t']:
            raise RuntimeError('Database LC_CTYPE does not support Chinese pg_trgm; create a UTF8 database with Chinese_China.936 (Windows) or C.UTF-8 locale')
