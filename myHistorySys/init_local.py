"""Create a new private localhost PostgreSQL cluster, never alter an existing one."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import quote

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--create-private-cluster',action='store_true',help='Explicitly create and start a separate PostgreSQL instance')
    parser.add_argument('--port',type=int,default=55439)
    args=parser.parse_args()
    if not args.create_private_cluster:
        parser.error('This creates another PostgreSQL instance. Existing-server deployments do not need this script; pass --create-private-cluster only when explicitly intended.')
    local=ROOT/'.local'
    local.mkdir(exist_ok=True)
    data=local/'postgres-data'
    initdb=shutil.which('initdb')
    pg_ctl=shutil.which('pg_ctl')
    psql=shutil.which('psql')
    if not all([initdb,pg_ctl,psql]):
        raise SystemExit('PostgreSQL bin tools missing from PATH')
    if data.exists():
        raise SystemExit('Local cluster already exists; use pg_ctl to start it, do not reinitialize')
    if (local/'database.url').exists():
        raise SystemExit('Local connection configuration already exists; refusing overwrite')
    password=secrets.token_urlsafe(32)
    pwfile=local/'init-password'
    pwfile.write_text(password,encoding='utf-8')
    try:
        locale='Chinese_China.936' if os.name=='nt' else 'C.UTF-8'
        subprocess.run([initdb,'-D',str(data),'-U','history_local','--encoding=UTF8',f'--locale={locale}',
                        '--auth-local=scram-sha-256','--auth-host=scram-sha-256','--pwfile',str(pwfile)],check=True)
    finally:
        pwfile.unlink(missing_ok=True)
    with (data/'postgresql.conf').open('a',encoding='utf-8') as stream:
        stream.write(f"\n# SpringHistory isolated local cluster\nlisten_addresses = '127.0.0.1'\nport = {args.port}\n")
    subprocess.run([pg_ctl,'-D',str(data),'-l',str(local/'postgres.log'),'-w','start'],check=True)
    child_env=os.environ.copy()
    child_env['PGPASSWORD']=password
    subprocess.run([psql,'-h','127.0.0.1','-p',str(args.port),'-U','history_local','-d','postgres',
                    '-v','ON_ERROR_STOP=1','-c','CREATE DATABASE springhistory'],env=child_env,check=True)
    url=f'postgresql://history_local:{quote(password,safe="")}@127.0.0.1:{args.port}/springhistory'
    (local/'database.url').write_text(url,encoding='utf-8')
    (local/'cluster.json').write_text(json.dumps({'port':args.port,'data':str(data),'pg_ctl':pg_ctl}),encoding='utf-8')
    print(f'Created isolated localhost cluster on port {args.port}; credentials saved only in .local/database.url')

if __name__=='__main__':
    main()
