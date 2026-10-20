"""Read only the public catalogue and chapter headers; never decode or change bodies."""
from pathlib import Path
import re
import struct


def scan_catalog(root):
    books = []
    for cal in sorted((Path(root) / 'lib').rglob('*.CAL')):
        raw = cal.read_bytes()
        if not raw.startswith(b'FTR_CATALOGUE1.0') or len(raw) < 72:
            continue
        end = struct.unpack_from('<I', raw, 60)[0]
        if not 68 < end < min(len(raw), 400):
            end = struct.unpack_from('<I', raw, 56)[0]
            if not 68 < end < min(len(raw), 400):
                continue
        try:
            title = raw[68:end].decode('gb18030')
        except UnicodeDecodeError:
            continue
        ftp = cal.with_suffix('.ftp')
        books.append({'id': cal.stem, 'title': title, 'project': str(ftp),
                      'available': ftp.is_file(), 'category': cal.parent.name})
    return books


def chapter_headers(root, book):
    """AMG record header: flags, title length, data offset, sizes, GBK title.

    Validate offsets and the following source-path boundary to reject matches in
    compressed content. Record indexes are local metadata, not printed page IDs.
    """
    project = Path(book['project']).resolve()
    project.relative_to(Path(root).resolve() / 'lib')
    raw = project.with_suffix('.AMG').read_bytes()
    if not raw.startswith(b'FTR_ARTI'):
        raise ValueError('Unrecognized chapter file')
    result = []
    for match in re.finditer(rb'\x01\x01([\x01-\xf0])', raw):
        start, size = match.start(), match[1][0]
        if start + 15 + size + 3 >= len(raw):
            continue
        data_at = struct.unpack_from('<I', raw, start + 3)[0]
        end = start + 15 + size
        if not end + 3 <= data_at <= min(end + 500, len(raw)):
            continue
        if not re.match(rb'[A-Za-z]:\\', raw[end:end + 3]):
            continue
        try:
            title = raw[start + 15:end].decode('gb18030')
        except UnicodeDecodeError:
            continue
        if not title or any(ord(c) < 32 for c in title):
            continue
        result.append({'index': len(result), 'title': title})
    return result


DIGITS = dict(zip('〇○零一二三四五六七八九', [0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))


def chinese_number(value):
    if value.isdecimal():
        return int(value)
    if all(c in DIGITS for c in value):
        return int(''.join(str(DIGITS[c]) for c in value))
    total = part = 0
    for c in value:
        if c in DIGITS:
            part = DIGITS[c]
        elif c in '十百千':
            total += (part or 1) * {'十': 10, '百': 100, '千': 1000}[c]
            part = 0
        else:
            raise ValueError(value)
    return total + part


def volume_key(title):
    found = re.search(r'卷\s*第?([0-9〇○零一二三四五六七八九十百千]+)(上|中|下)?', title)
    if not found:
        return None
    return chinese_number(found[1]), found[2] or ''


def find_chapter(chapters, volume):
    key = volume_key('卷' + str(volume))
    matches = [c for c in chapters if volume_key(c['title']) == key]
    if len(matches) != 1:
        raise ValueError(f'卷次未唯一匹配：{volume}（{len(matches)}项）')
    return matches[0]
