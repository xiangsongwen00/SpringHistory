"""Read the independent localhost text API; never upgrade historical verification state."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError,URLError
from urllib.parse import quote,urlencode
from urllib.request import urlopen


def main():
    parser=argparse.ArgumentParser(description='检索独立原文库，或读取命中章的完整上下文')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--query')
    modes.add_argument('--chapter',help='实际chapter_id，不以史书卷号猜测index')
    parser.add_argument('--book-id')
    parser.add_argument('--characters',action='store_true',help='配合--chapter读取原文、独立字形恢复视图和待核记录')
    parser.add_argument('--limit',type=int,default=10,choices=range(1,101),metavar='1-100')
    parser.add_argument('--output',type=Path,help='可选证据JSON路径；含原文，请勿直接批量发布')
    args=parser.parse_args()
    if args.characters and not args.chapter:parser.error('--characters requires --chapter')
    base=os.environ.get('HISTORY_API_BASE','http://127.0.0.1:18866').rstrip('/')
    if args.chapter:
        endpoint='/chapters/'+quote(args.chapter,safe='')
        if args.characters:endpoint+='/characters'
    else:
        params={'q':args.query,'limit':args.limit}
        if args.book_id: params['book_id']=args.book_id
        endpoint='/search?'+urlencode(params)
    try:
        with urlopen(base+endpoint,timeout=25) as response: result=json.load(response)
    except HTTPError as exc:
        raise SystemExit(f'原文API返回HTTP {exc.code}；请检查书章ID、查询范围或服务状态') from None
    except (URLError,TimeoutError):
        raise SystemExit('无法连接原文API；请先双击“启动原文查询服务.cmd”') from None
    envelope={'queried_at':datetime.now(timezone.utc).isoformat(),'endpoint':endpoint,
              'verification_note':'机器解码状态不等于人工校勘；须阅读上下文并另记核对范围',
              'result':result}
    content=json.dumps(envelope,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(content,encoding='utf-8')
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(content,end='')

if __name__=='__main__':main()
