"""Extract archival article bytes using the installed DLL in an isolated x86 process."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import struct

MAX_ARTICLE = 64*1024*1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--book', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if ctypes.sizeof(ctypes.c_void_p) != 4: raise RuntimeError('Use x86 Python')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.book): raise ValueError('Invalid book ID')
    root = Path(args.root).resolve()
    paths = list((root/'lib').rglob(args.book+'.AMG'))
    if len(paths)!=1: raise ValueError('Book must resolve uniquely')
    source = paths[0]
    header = source.read_bytes()[:26]
    if not header.startswith(b'FTR_ARTI') or header[20:22] != b'SA':
        raise ValueError('Unsupported article archive header')
    count = struct.unpack_from('<I', header, 22)[0]
    if not 0 < count < 1000000: raise ValueError('Implausible article count')
    output=Path(args.output).resolve()
    if output == root or root in output.parents: raise ValueError('Output must be outside source library')
    output.mkdir(parents=True,exist_ok=True)
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    dll = ctypes.CDLL(str(root/'Ftrquery.dll'))
    signatures = {'FTR_OpenArticleMgr': [ctypes.c_char_p],
        'FTR_CloseArticleMgr':[ctypes.c_int],
        'FTR_GetArticleInfo':[ctypes.c_int,ctypes.c_int,ctypes.c_void_p],
        'FTR_GetArticleData':[ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]}
    for name,types in signatures.items():
        getattr(dll,name).argtypes=types
        getattr(dll,name).restype=ctypes.c_int
    handle=dll.FTR_OpenArticleMgr(str(source.with_suffix('')).encode('gbk',errors='strict'))
    if not handle: raise RuntimeError('FTR_OpenArticleMgr failed')
    part=output/'manifest.part.jsonl'
    try:
        with part.open('w',encoding='utf-8') as stream:
            for index in range(count):
                info=ctypes.create_string_buffer(4096)
                if dll.FTR_GetArticleInfo(handle,index,info)!=1:
                    raise RuntimeError(f'Article info failed: {index}')
                title=info.raw[260:516].split(b'\0',1)[0].decode('gb18030',errors='strict')
                original=info.raw[4:260].split(b'\0',1)[0].decode('gb18030',errors='strict')
                size=struct.unpack_from('<I',info.raw,520)[0]
                if not 0<size<=MAX_ARTICLE: raise ValueError(f'Invalid article size {index}: {size}')
                buffer=ctypes.create_string_buffer(size+1)
                capacity=ctypes.c_int(size+1)
                # Return value is a BOOL, NOT the byte count. Length is in info.
                if dll.FTR_GetArticleData(handle,index,buffer,ctypes.byref(capacity))!=1:
                    raise RuntimeError(f'Article decode failed: {index}')
                raw=buffer.raw[:size]
                path=output/f'{index:06d}.rtf'
                path.write_bytes(raw)
                row={'chapter_index':index,'chapter_title':title,'original_path':original,
                     'raw_file':path.name,'raw_size':size,'raw_sha256':hashlib.sha256(raw).hexdigest()}
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                stream.flush()
        part.replace(output/'manifest.jsonl')
        print(json.dumps({'book_id':args.book,'chapters':count,'state':'raw_extracted'}),flush=True)
    finally:
        dll.FTR_CloseArticleMgr(handle)

if __name__=='__main__': main()
