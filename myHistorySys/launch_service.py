"""One-click local cluster/API launcher. Does not install a system service."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser
from historysys.db import ROOT,connect,migrate
from psycopg.adapt import Loader

API='http://127.0.0.1:18866'
FLAGS=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

def api_ready():
    try:
        with urlopen(API+'/health',timeout=3) as response:
            health=json.load(response)
        with urlopen(API+'/openapi.json',timeout=3) as response:
            info=json.load(response)
        return health.get('status')=='ok' and health.get('database')=='connected' and info.get('info',{}).get('title')=='SpringHistory text service'
    except Exception:
        return False

def ensure_cluster():
    local=ROOT/'.local'
    data=(local/'postgres-data').resolve()
    config_file=local/'cluster.json'
    if not config_file.exists() or not (data/'PG_VERSION').exists() or not (local/'database.url').exists():
        raise RuntimeError('Private cluster missing. First run init_local.py; existing external databases are not changed.')
    config=json.loads(config_file.read_text(encoding='utf-8'))
    if Path(config['data']).resolve()!=data:
        raise RuntimeError('Cluster metadata points outside this project; refusing to start it')
    pg_ctl=shutil.which('pg_ctl') or config.get('pg_ctl')
    if not pg_ctl or Path(pg_ctl).name.lower() not in ('pg_ctl','pg_ctl.exe') or not Path(pg_ctl).is_file():
        raise RuntimeError('PostgreSQL pg_ctl executable unavailable')
    status=subprocess.run([pg_ctl,'-D',str(data),'status'],capture_output=True,creationflags=FLAGS)
    if status.returncode!=0:
        if status.returncode!=3:
            raise RuntimeError('Cannot establish private cluster status; inspect .local/postgres.log')
        subprocess.run([pg_ctl,'-D',str(data),'-l',str(local/'postgres.log'),'-w','start'],
                       check=True,capture_output=True,creationflags=FLAGS,timeout=40)
    with connect() as conn:
        # Windows PostgreSQL16 can return an ACP-encoded installation path despite UTF8 DB encoding.
        class RawText(Loader):
            def load(self,data):
                return bytes(data)
        with conn.cursor() as cursor:
            cursor.adapters.register_loader('text',RawText)
            raw=cursor.execute('SHOW data_directory').fetchone()['data_directory']
        try:
            actual_path=bytes(raw).decode('utf-8')
        except UnicodeDecodeError:
            if os.name!='nt':
                raise
            actual_path=bytes(raw).decode('gb18030')
        actual=Path(actual_path).resolve()
        if actual!=data:
            raise RuntimeError('Configured connection is not this project private cluster; refusing to continue')
        schema_ready=conn.execute("SELECT to_regclass('history.chapters') IS NOT NULL AND to_regclass('history.paragraphs') IS NOT NULL AS ready").fetchone()['ready']
    # Launching a reader must not rebuild deliberately deferred indexes during a full import.
    # Schema upgrades remain an explicit `python -m historysys.importer --migrate` operation.
    if not schema_ready:
        migrate()

def main():
    ensure_cluster()
    if not api_ready():
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1',18866))==0:
                raise RuntimeError('Port18866 already occupied or API unhealthy; no unrelated process will be stopped')
        with (ROOT/'.local'/'api.log').open('ab') as log:
            subprocess.Popen([sys.executable,str(ROOT/'start_service.py')],cwd=ROOT,stdout=log,stderr=log,
                             stdin=subprocess.DEVNULL,creationflags=FLAGS)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if api_ready():
                break
            time.sleep(.25)
        else:
            raise RuntimeError('API did not become healthy; inspect .local/api.log')
    webbrowser.open(API+'/docs')
    print('SpringHistory PostgreSQL API ready: '+API+'/docs')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Do not print exception details containing possible connection credentials.
        print('Startup failed: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
