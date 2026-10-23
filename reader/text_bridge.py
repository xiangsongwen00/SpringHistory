"""Fixed loopback, read-only proxy for the independently managed text API."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:18866'
MAX_BYTES = 64 * 1024 * 1024


class TextServiceError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def endpoint(path, query):
    allowed = {
        '/health': set(), '/restoration': set(),
        '/books': {'limit','offset'},
        '/search': {'q','book_id','limit','offset','normalized'},
    }
    if re.fullmatch(r'/books/[A-Za-z0-9_-]+/chapters',path):
        keys={'limit','offset'}
    elif re.fullmatch(r'/chapters/[A-Za-z0-9_-]+:[0-9]+(?:/(?:characters|paragraphs|assets))?',path):
        keys={'limit','offset'} if path.endswith('/paragraphs') else set()
    elif re.fullmatch(r'/chapters/[A-Za-z0-9_-]+:[0-9]+/assets/[0-9]+/download',path):
        keys={'part'}
    elif path in allowed: keys=allowed[path]
    else: raise TextServiceError('原文接口不存在',404)
    params=parse_qs(query,keep_blank_values=True,max_num_fields=10)
    if set(params)-keys or any(len(v)!=1 for v in params.values()):
        raise TextServiceError('原文查询参数无效',400)
    if sum(len(v[0]) for v in params.values())>1000:
        raise TextServiceError('原文查询参数过长',400)
    return path+('?' + urlencode({k:v[0] for k,v in params.items()}) if params else '')


def fetch_text(path,query=''):
    route=endpoint(path,query)
    try:
        with urlopen(Request(BASE+route,headers={'Accept':'application/json'}),timeout=25) as response:
            body=response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:raise TextServiceError('原文响应超过大小限制',502)
            return body,response.headers.get_content_type(),response.headers.get('X-Content-SHA256')
    except HTTPError as e:
        messages={404:'未找到原文章节或资源',409:'原文与核对记录版本不一致，请重新导入证据',
                  422:'查询参数不符合要求',503:'原文数据库暂不可用'}
        raise TextServiceError(messages.get(e.code,'原文服务请求失败'),e.code) from None
    except (URLError,TimeoutError,OSError):
        raise TextServiceError('原文服务未连接，请双击项目根目录“启动原文查询服务.cmd”；阅读器不会自动启动数据库') from None


def text_json(path,query=''):
    return json.loads(fetch_text(path,query)[0])


def source_reference(source_id,sources):
    from hanji_catalog import find_chapter,volume_key
    source=sources.get(source_id)
    if source is None:raise TextServiceError('未登记此出处',404)
    book=source.get('bookId') or {'旧唐书':'B01-137','新唐书':'B01-138','资治通鉴':'B02-163'}.get(source['book'])
    if not book:raise TextServiceError('出处尚未登记原文书库编号',404)
    if source.get('chapterId'):
        chapter=text_json('/chapters/'+quote(source['chapterId'],safe=':'))
        if chapter['book_id']!=book:raise TextServiceError('出处书库与章ID不匹配',409)
        if source.get('chapterTitle') and chapter['title']!=source['chapterTitle']:
            raise TextServiceError('出处篇名与数据库篇题不匹配',409)
        if not source.get('chapterTitle') and source.get('volume') and volume_key(chapter['title'])!=volume_key('卷'+source['volume']):
            raise TextServiceError('出处卷次与数据库卷题不匹配',409)
    else:
        rows=[];offset=0
        while True:
            page=text_json('/books/'+book+'/chapters',urlencode({'limit':500,'offset':offset}))
            rows.extend(page)
            if len(page)<500:break
            offset+=500
            if offset>100000:raise TextServiceError('书目篇章超过定位上限',502)
        try: matched=find_chapter(rows,source['volume'])
        except ValueError as e:raise TextServiceError(str(e),409) from None
        chapter=text_json('/chapters/'+matched['chapter_id'])
    return dict(source,id=source_id,bookId=book,chapterId=chapter['chapter_id'],
                chapter=chapter['title'],source_sha256=chapter['source_sha256'],
                decoder=chapter['decoder'],verification_status=chapter['verification_status'],
                textVerified=False,storage='postgresql')
