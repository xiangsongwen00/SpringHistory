"""Double-click launcher: start a hidden local service, then open the case hub."""
from pathlib import Path
import argparse
import ctypes
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

HERE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:18865'

def health():
    try:
        with urllib.request.urlopen(URL + '/api/bootstrap', timeout=2) as response:
            data = json.load(response)
        if data.get('app') == 'history-reader' and data.get('apiVersion') == 3:
            return data
        raise RuntimeError('18865端口运行的是旧版服务或其他程序，请先关闭旧服务再启动。')
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None

def ensure_text_service():
    """An explicit reader launch may start its API, never PostgreSQL or DDL."""
    runtime=HERE.parent/'myHistorySys/.venv/Scripts/python.exe'
    launcher=HERE.parent/'myHistorySys/launch_service.py'
    if not runtime.is_file():return False
    result=subprocess.run([str(runtime),str(launcher),'--no-browser'],cwd=launcher.parent,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0,
                          timeout=40)
    return result.returncode==0


def launch(open_browser=True):
    try:text_ready=ensure_text_service()
    except (OSError,subprocess.TimeoutExpired):text_ready=False
    state = health()
    if not state:
        python = HERE / '.venv' / 'Scripts' / 'python.exe'
        if not python.is_file() or not (HERE / 'dist' / 'local.html').is_file():
            raise RuntimeError('依赖或页面尚未安装。请先在reader目录运行“安装阅读系统.ps1”。')
        with (HERE / 'reader-service.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen([str(python), str(HERE/'local_service.py')], cwd=HERE,
                stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(60):
            state = health()
            if state: break
            if process.poll() is not None:
                raise RuntimeError('阅读服务启动失败，详情见reader/reader-service.log。')
            time.sleep(.25)
        if not state: raise RuntimeError('阅读服务启动超时，详情见reader/reader-service.log。')
    if open_browser: webbrowser.open(URL, new=2)
    return {'url':URL,'cases':len(state['cases']),'documents':len(state['docs']),
            'textApiReady':text_ready}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(launch(not args.no_browser)))
    except Exception as error:
        if not args.no_browser:
            ctypes.windll.user32.MessageBoxW(0,str(error),'史地阅读室启动失败',0x10)
        else: print(str(error),file=sys.stderr)
        sys.exit(1)
