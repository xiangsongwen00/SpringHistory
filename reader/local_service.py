"""Loopback-only reader, read-only catalogue and allowlisted native citation bridge."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hmac
import importlib.util
import json
import mimetypes
import os
import re
import secrets
import threading
import traceback
import uuid
from urllib.parse import unquote, urlsplit

from hanji_catalog import scan_catalog, chapter_headers, find_chapter
from endsplash_guard import EndSplashGuard
from text_bridge import fetch_text, source_reference, TextServiceError

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
HANJI = Path(os.environ.get('HANJI_ROOT', 'E:/汉籍全文检索系统')).resolve()
EXE = HANJI / '汉籍全文检索系统.exe'
DOCS_ROOT = WORKSPACE / 'docs'
SOURCES = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))


class Library:
    def __init__(self, root=HANJI):
        self.root = Path(root)
        self.books = scan_catalog(root)
        self.by_id = {b['id']: b for b in self.books}
        self.headers = {}

    def chapters(self, book_id):
        if book_id not in self.by_id:
            raise ValueError('未收录此书库编号')
        if book_id not in self.headers:
            self.headers[book_id] = chapter_headers(self.root, self.by_id[book_id])
        return self.headers[book_id]

    def source(self, source_id):
        if source_id not in SOURCES:
            raise ValueError('未登记此出处')
        source = SOURCES[source_id]
        books = [b for b in self.books if b['title'] == source['book'] and b['available']]
        if len(books) != 1:
            raise ValueError('书目未唯一匹配')
        book = books[0]
        if source.get('nativeAvailable') is False:
            return dict(source, id=source_id, bookId=book['id'],
                        chapter=source['chapterTitle'], chapterIndex=None,
                        catalogueVerified=False, bookCatalogueVerified=True,
                        textVerified=False, automationVerified=False)
        if source.get('chapterTitle'):
            matches = [c for c in self.chapters(book['id']) if c['title'] == source['chapterTitle']]
            if len(matches) != 1:
                raise ValueError('篇名未唯一匹配')
            chapter = matches[0]
        else:
            chapter = find_chapter(self.chapters(book['id']), source['volume'])
        return dict(source, id=source_id, bookId=book['id'], chapter=chapter['title'],
                    chapterIndex=chapter['index'], catalogueVerified=True,
                    textVerified=False, automationVerified=False)


def load_docs(root=DOCS_ROOT):
    root = Path(root).resolve()
    paths = []
    for path in sorted(root.rglob('*.md')):
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        paths.append(path)
    return [{'path': p.relative_to(WORKSPACE).as_posix(), 'label': p.stem,
             'content': p.read_text(encoding='utf-8')}
            for p in paths if p.is_file()]


def load_cases(docs):
    manifest = DOCS_ROOT / 'cases.json'
    if not manifest.is_file(): return []
    cases = json.loads(manifest.read_text(encoding='utf-8'))['cases']
    allowed = {doc['path'] for doc in docs}
    ids = set()
    for case in cases:
        if case['id'] in ids: raise ValueError('案例编号重复')
        ids.add(case['id'])
        if case['entry'] not in case['documents']:
            raise ValueError('案例入口须列入该案例文档清单')
        targets = [case['entry'], *case['documents'], *[y['doc'] for y in case.get('years', [])]]
        if any(path not in allowed for path in targets): raise ValueError('案例引用了docs外或不存在的文档')
        if case.get('documentGroups') is not None:
            grouped = [path for group in case['documentGroups'] for path in group['documents']]
            if len(grouped) != len(set(grouped)) or set(grouped) != set(case['documents']):
                raise ValueError('案例分组须完整且不重复覆盖文档清单')
        prefix = 'docs/cases/' + case['id'] + '/'
        for old, new in case.get('legacyPaths', {}).items():
            if not old.startswith(prefix) or '..' in old.split('/') or '\\' in old or new not in case['documents']:
                raise ValueError('案例旧路径映射越界或不存在')
    return cases


class AppState:
    def __init__(self, library, port, driver=None):
        self.library = library
        self.origin = f'http://127.0.0.1:{port}'
        self.token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.driver = driver
        self.busy = False
        self.guard = None

    def submit(self, source_id, query, mode):
        source = self.library.source(source_id)
        query = str(query).strip()
        if len(query) > 120 or any(ord(c) < 32 for c in query):
            raise ValueError('检索词须为120字以内的单行文字')
        # The catalogue is simplified GBK. Avoid silently sending unrepresentable text.
        try:
            query.encode('gbk')
        except UnicodeEncodeError:
            raise ValueError('检索词含本机GBK字库无法表示的字，请改用简体短词')
        if mode not in ('auto', 'book'):
            raise ValueError('不支持此打开模式')
        if self.busy:
            raise RuntimeError('上一项打开操作仍在进行，请稍后重试')
        job_id = uuid.uuid4().hex
        self.busy = True
        self.jobs[job_id] = {'id': job_id, 'state': 'running', 'stage': 'queued',
                             'message': '等待打开本机汉籍', 'source': source,
                             'textVerified': False}

        def work():
            pythoncom = None
            try:
                if self.driver is None and mode == 'auto':
                    import pythoncom
                    pythoncom.CoInitialize()
                from hanji_driver import drive
                driver = self.driver or drive
                def report(**fields):
                    with self.lock:
                        self.jobs[job_id].update(fields)
                result = driver(EXE, self.library.by_id[source['bookId']]['project'],
                                source['book'], source['chapter'], query, mode, report)
                with self.lock:
                    self.jobs[job_id].update(result, state='done')
            except Exception as error:
                error_path = HERE / 'diagnostics' / 'bridge-latest-error.txt'
                error_path.parent.mkdir(exist_ok=True)
                error_path.write_text(traceback.format_exc(), encoding='utf-8')
                with self.lock:
                    self.jobs[job_id].update(state='error', stage='stopped',
                        message=f'自动打开未完成：{error}。可使用“仅启动书库”或按出处卡手动选择。')
            finally:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
                with self.lock:
                    self.busy = False
        self.executor.submit(work)
        return self.jobs[job_id]


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send_bytes(self, status, body, kind='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))

        def valid_host(self):
            return self.headers.get('Host') == urlsplit(state.origin).netloc

        def do_GET(self):
            if not self.valid_host():
                return self.json({'error': '非法主机名'}, 403)
            path = unquote(urlsplit(self.path).path)
            try:
                if path.startswith('/api/text/source/'):
                    return self.json(source_reference(path.rsplit('/',1)[-1],SOURCES))
                if path.startswith('/api/text/'):
                    body,kind,digest=fetch_text(path[len('/api/text'):],urlsplit(self.path).query)
                    if path.endswith('/download'):
                        self.send_response(200)
                        self.send_header('Content-Type','application/octet-stream')
                        self.send_header('Content-Disposition','attachment; filename="history-asset.bin"')
                        self.send_header('Content-Length',str(len(body)))
                        self.send_header('X-Content-Type-Options','nosniff')
                        if digest:self.send_header('X-Content-SHA256',digest)
                        self.end_headers();self.wfile.write(body);return
                    return self.send_bytes(200,body,'application/json; charset=utf-8')
                if path == '/api/bootstrap':
                    docs = load_docs()
                    return self.json({'app': 'history-reader', 'apiVersion': 3,
                        'token': state.token, 'docs': docs, 'cases': load_cases(docs),
                        'sources': SOURCES, 'books': [dict(id=b['id'], title=b['title'],
                        available=b['available'], category=b['category']) for b in state.library.books],
                        'driverInstalled': importlib.util.find_spec('pywinauto') is not None,
                        'exeExists': EXE.is_file(), 'automationVerified': False,
                        'endSplashGuard': state.guard.status() if state.guard else None})
                if path.startswith('/api/source/'):
                    return self.json(state.library.source(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/chapters/'):
                    return self.json(state.library.chapters(path.rsplit('/', 1)[-1]))
                if path.startswith('/api/job/'):
                    with state.lock:
                        job = state.jobs.get(path.rsplit('/', 1)[-1])
                        return self.json(job or {'error': '操作不存在'}, 200 if job else 404)
                # Serve only built reader assets; never expose workspace, .venv or book bodies.
                relative = 'local.html' if path == '/' else path.lstrip('/')
                target = (HERE / 'dist' / relative).resolve()
                target.relative_to((HERE / 'dist').resolve())
                if not target.is_file():
                    return self.json({'error': '页面不存在；请先运行构建'}, 404)
                kind = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                if target.suffix in ('.js', '.mjs'):
                    kind = 'text/javascript'
                return self.send_bytes(200, target.read_bytes(), kind)
            except TextServiceError as error:
                return self.json({'error':str(error)},error.status)
            except (ValueError, OSError) as error:
                return self.json({'error': str(error)}, 404)

        def do_POST(self):
            if (not self.valid_host() or self.headers.get('Origin') != state.origin or
                not hmac.compare_digest(self.headers.get('X-Reader-Token', ''), state.token)):
                return self.json({'error': '本机来源或会话校验失败'}, 403)
            if urlsplit(self.path).path != '/api/open':
                return self.json({'error': '接口不存在'}, 404)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    return self.json({'error': '请求过大或为空'}, 400)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('请求格式不正确')
                with state.lock:
                    result = state.submit(body.get('sourceId'), body.get('query', ''), body.get('mode', 'auto'))
                return self.json(result, 202)
            except (ValueError, TypeError, KeyError) as error:
                return self.json({'error': str(error)}, 400)
            except RuntimeError as error:
                return self.json({'error': str(error)}, 409)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18865)
    parser.add_argument('--catalog-only', action='store_true')
    args = parser.parse_args()
    library = Library()
    if args.catalog_only:
        print(json.dumps({'books': len(library.books),
              'sources': {key: library.source(key) for key in SOURCES}}, ensure_ascii=False, indent=2))
        return
    state = AppState(library, args.port)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(state))
    state.guard = EndSplashGuard(HANJI / 'EndSplash.exe', HERE / 'diagnostics' / 'endsplash-events.jsonl').start()
    print(f'本机阅读系统：{state.origin}（书目{len(library.books)}种；按 Ctrl+C 停止）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.guard.stop()
        state.executor.shutdown(wait=False)


if __name__ == '__main__':
    main()
