"""Resolve a registered local citation; native actions require explicit --open."""
import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('服务重定向已拒绝')


def run(args):
    origin = args.base.rstrip('/')
    parts = urlsplit(origin)
    if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or parts.path or parts.query or parts.fragment or parts.username:
        raise ValueError('--base 必须是 http://127.0.0.1:端口')
    opener = build_opener(NoRedirect())

    def request(path, body=None, token=None):
        headers = {'Accept': 'application/json'}
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin, 'X-Reader-Token': token})
        req = Request(origin + path, data=None if body is None else json.dumps(body).encode('utf-8'), headers=headers)
        with opener.open(req, timeout=min(15, args.timeout)) as response:
            return json.load(response)

    source = request('/api/source/' + quote(args.source, safe=''))
    if not args.open:
        return {'action': 'resolve_only', 'source': source,
                'notice': '仅解析目录，未操作窗口，未读取或校勘正文'}, 0
    bootstrap = request('/api/bootstrap')
    job = request('/api/open', {'sourceId': args.source, 'query': args.query if args.query is not None else source.get('query', ''),
                               'mode': args.mode}, bootstrap['token'])
    deadline = time.monotonic() + args.timeout
    while job.get('state') == 'running' and time.monotonic() < deadline:
        time.sleep(0.5)
        job = request('/api/job/' + quote(job['id'], safe=''))
    if job.get('state') == 'running':
        return {'action': 'open', 'timedOut': True, 'job': job,
                'notice': '客户端等待超时，服务中的原操作可能继续；不要重复点击。尚未校勘正文。'}, 2
    return {'action': 'open', 'job': job,
            'notice': '驱动状态按服务原样返回；任务完成不代表正文校勘，须实际读取上下文。'}, 0 if job.get('state') == 'done' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='reader/sources.json 中的出处 ID，例如 J18')
    parser.add_argument('--base', default='http://127.0.0.1:18865')
    parser.add_argument('--query', help='替换默认检索词')
    parser.add_argument('--open', action='store_true', help='明确授权本次真实窗口操作')
    parser.add_argument('--mode', choices=['auto', 'book'], default='auto')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout 必须大于零')
    try:
        result, code = run(args)
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode('utf-8'))
        except (ValueError, UnicodeError):
            detail = str(error)
        result, code = {'error': detail, 'httpStatus': error.code}, 1
    except (URLError, OSError, ValueError, KeyError) as error:
        result, code = {'error': str(error)}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
