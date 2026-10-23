"""Read local, source-bound character notes without changing database rows."""
from functools import lru_cache
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:sys.path.insert(0,str(PROJECT))
from readerTool.character_reading import reading_view

NOTES=PROJECT/'readerTool/.local/unknowns/chapter-notes.json'


@lru_cache(maxsize=1)
def _load(path,mtime,size):
    if size>32*1024*1024:raise ValueError('Character note file exceeds size limit')
    return json.loads(Path(path).read_text(encoding='utf8'))['chapters']


def chapter_characters(chapter):
    available=NOTES.is_file()
    if available:
        stat=NOTES.stat();records=_load(str(NOTES),stat.st_mtime_ns,stat.st_size)
        record=records.get(chapter['chapter_id'])
    else:record=None
    result=reading_view(chapter,record)
    result.update(chapter_id=chapter['chapter_id'],source_sha256=chapter['source_sha256'],
                  decoder=chapter['decoder'],verification_status=chapter['verification_status'],
                  character_report_available=available)
    return result
