"""Isolated read-only ABI experiment. Requires 32-bit Python. No GUI driver."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--book', default='B01-137')
    parser.add_argument('--index', type=int, default=20)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.index < 0 or not re.fullmatch(r'[A-Za-z0-9_-]+',args.book):
        parser.error('Invalid book/index')
    if ctypes.sizeof(ctypes.c_void_p) != 4: raise RuntimeError('32-bit interpreter required')
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    if output == root or root in output.parents: parser.error('Output must be outside source library')
    matches = list((root / 'lib').rglob(args.book+'.AMG'))
    if len(matches) != 1: raise RuntimeError('Book not unique')
    amg = matches[0]
    dll = ctypes.CDLL(str(root / 'Ftrquery.dll'))
    dll.FTR_OpenArticleMgr.argtypes = [ctypes.c_char_p]
    dll.FTR_OpenArticleMgr.restype = ctypes.c_int
    dll.FTR_GetArticleInfo.argtypes = [ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    dll.FTR_GetArticleInfo.restype = ctypes.c_int
    dll.FTR_GetArticleData.argtypes = [ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
    dll.FTR_GetArticleData.restype = ctypes.c_int
    dll.FTR_CloseArticleMgr.argtypes = [ctypes.c_int]
    handle = dll.FTR_OpenArticleMgr(str(amg.with_suffix('')).encode('gbk'))
    print(json.dumps({'opened':handle},ensure_ascii=True),flush=True)
    if not handle: raise RuntimeError('Native article manager open failed')
    try:
        info = ctypes.create_string_buffer(4096)
        result = dll.FTR_GetArticleInfo(handle,args.index,info)
        print(json.dumps({'infoResult':result,'infoHead':info.raw[:32].hex(),
            'field520':struct.unpack_from('<I',info.raw,520)[0]},ensure_ascii=True),flush=True)
        count = struct.unpack_from('<I',info.raw,520)[0]
        if result != 1 or not 0 < count <= 64*1024*1024:
            raise RuntimeError('Invalid article info/size')
        capacity = ctypes.c_int(count+1)
        buffer = ctypes.create_string_buffer(capacity.value)
        success = dll.FTR_GetArticleData(handle,args.index,buffer,ctypes.byref(capacity))
        print(json.dumps({'dataResult':success,'expectedLength':count,'firstNul':buffer.raw.find(b'\0'),
            'capacityAfter':capacity.value,'head':buffer.raw[:80].hex()},ensure_ascii=True),flush=True)
        if success != 1 or not 0 < count <= len(buffer): raise RuntimeError('Native article data invalid')
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(buffer.raw[:count])
        print(json.dumps({'bytes':count,'sha256':hashlib.sha256(buffer.raw[:count]).hexdigest()},ensure_ascii=True))
    finally:
        dll.FTR_CloseArticleMgr(handle)

if __name__ == '__main__': main()
