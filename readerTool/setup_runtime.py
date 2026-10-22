"""Fetch a pinned official Python x86 embeddable runtime into ignored local storage."""
import hashlib
from pathlib import Path
import subprocess
import urllib.request
import zipfile

URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-win32.zip'
SHA256='084b9eb24cb848605c895d05b738fbc2572efc8b4c18c415a824065864a2b853'
HERE=Path(__file__).resolve().parent


def main():
    local=HERE/'.local'; local.mkdir(exist_ok=True)
    archive=local/'python32.zip'
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
        part=archive.with_suffix('.download')
        with urllib.request.urlopen(URL,timeout=60) as response, part.open('wb') as target:
            while block:=response.read(1024*1024): target.write(block)
        if hashlib.sha256(part.read_bytes()).hexdigest()!=SHA256:
            raise ValueError('Python download SHA256 mismatch; runtime not installed')
        part.replace(archive)
    destination=local/'python32'
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            resolved=(destination/item.filename).resolve()
            if destination.resolve() not in resolved.parents:
                raise ValueError('Unsafe zip path')
        zipped.extractall(destination)
    subprocess.run([str(destination/'python.exe'),'-c',
                    'import ctypes; assert ctypes.sizeof(ctypes.c_void_p)==4; print("Python x86 ready")'],
                   check=True)

if __name__=='__main__': main()
