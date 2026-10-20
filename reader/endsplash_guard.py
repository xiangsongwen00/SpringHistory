"""Suppress only the EndSplash executable explicitly named by the user."""
from pathlib import Path
import json
import threading
import time
import psutil


def target_matches(actual, expected):
    return bool(actual) and str(Path(actual).resolve()).casefold() == str(Path(expected).resolve()).casefold()


class EndSplashGuard:
    def __init__(self, target, log_path=None, interval=.1):
        self.target = Path(target).resolve()
        self.log_path = Path(log_path) if log_path else None
        self.interval = interval
        self.stopped = threading.Event()
        self.thread = None
        self.closed = 0
        self.last_error = None

    def scan(self):
        for process in psutil.process_iter(['name', 'exe']):
            try:
                if (process.info['name'] or '').casefold() != 'endsplash.exe': continue
                if not target_matches(process.info['exe'], self.target): continue
                process.terminate()
                self.closed += 1
                if self.log_path:
                    self.log_path.parent.mkdir(exist_ok=True)
                    with self.log_path.open('a', encoding='utf-8') as output:
                        output.write(json.dumps({'time':time.time(),'pid':process.pid,
                            'exe':str(self.target),'action':'terminated'}, ensure_ascii=False)+'\n')
            except psutil.NoSuchProcess:
                pass
            except (psutil.Error, OSError) as error:
                self.last_error = str(error)

    def start(self):
        def run():
            while not self.stopped.is_set():
                self.scan()
                self.stopped.wait(self.interval)
        self.thread = threading.Thread(target=run, name='Hanji-EndSplash-guard', daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stopped.set()
        if self.thread: self.thread.join(timeout=2)

    def status(self):
        return {'active': bool(self.thread and self.thread.is_alive()), 'closed':self.closed,
                'target':str(self.target), 'lastError':self.last_error, 'intervalMs':int(self.interval*1000)}
