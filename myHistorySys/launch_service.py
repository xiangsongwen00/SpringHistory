"""Start the API against an existing database; never start PostgreSQL implicitly."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser
from historysys.db import ROOT,connect

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

def ensure_database():
    """Read-only preflight; database lifecycle remains with its administrator."""
    try:
        with connect() as conn:
            ready=conn.execute("SELECT to_regclass('history.chapters') IS NOT NULL AND to_regclass('history.paragraphs') IS NOT NULL AS ready").fetchone()['ready']
            if not ready:
                raise RuntimeError('History schema missing. Import or restore the database explicitly before starting the API.')
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError('Cannot connect to the configured PostgreSQL database. Start your database service and check the local connection configuration; no database instance was started.') from None


def main():
    parser=argparse.ArgumentParser(description='Start only the query API; connect to your existing PostgreSQL service')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    ensure_database()
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
    if not args.no_browser:
        webbrowser.open(API+'/docs')
    print('SpringHistory PostgreSQL API ready: '+API+'/docs')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Do not print exception details containing possible connection credentials.
        print('Startup failed: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
