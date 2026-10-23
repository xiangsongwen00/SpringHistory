"""Preserve exact pict/object groups; decode only unambiguous picture hex data.

Offsets are byte positions in the original RTF, not plain-text positions.
Objects may contain picture fallback groups; both are retained and linked.
No OLE execution, external conversion, or guessed image rendering.
"""
import hashlib
import re

TOKEN = re.compile(rb"\\'[0-9a-fA-F]{2}|\\[a-zA-Z]+-?\d* ?|\\[^a-zA-Z]|[{}]|[^\\{}]+")
KINDS = {b'\\pict': 'pict', b'\\object': 'object'}


def extract_assets(raw):
    if not raw.startswith(b'{\\rtf') or re.search(rb'\\bin\d+', raw):
        raise ValueError('Expected non-binary RTF')
    stack = []
    groups = []
    for match in TOKEN.finditer(raw):
        token = match.group()
        if token == b'{':
            stack.append({'start': match.start(), 'kind': None, 'first': True})
        elif token == b'}':
            if not stack:
                raise ValueError('Unbalanced RTF')
            group = stack.pop()
            if group['kind']:
                group['end'] = match.end()
                groups.append(group)
        elif stack:
            frame = stack[-1]
            if frame['first'] and token.strip():
                frame['kind'] = KINDS.get(token.strip())
                frame['first'] = False
    if stack:
        raise ValueError('Truncated RTF')
    results = []
    for group in sorted(groups, key=lambda g: g['start']):
        data = raw[group['start']:group['end']]
        payload = None
        fmt = 'ole_rtf' if group['kind'] == 'object' else 'unknown_picture_rtf'
        if group['kind'] == 'pict':
            # Ignore nested property groups. The direct group's remaining text
            # must be purely hex, never concatenate metadata or OLE content.
            depth = 0
            literals = []
            for match in TOKEN.finditer(data):
                token = match.group()
                if token == b'{': depth += 1
                elif token == b'}': depth -= 1
                elif depth == 1:
                    if token.startswith(b'\\'):
                        control = token.strip()
                        if control in (b'\\pngblip', b'\\jpegblip', b'\\emfblip'):
                            fmt = control[1:].decode('ascii')
                        elif re.fullmatch(rb'\\wmetafile\d+', control): fmt = 'wmf'
                        elif re.fullmatch(rb'\\dibitmap\d+', control): fmt = 'dib'
                    else: literals.append(token)
            encoded = re.sub(rb'\s+', b'', b''.join(literals))
            if encoded and len(encoded) % 2 == 0 and re.fullmatch(rb'[0-9a-fA-F]+', encoded):
                payload = bytes.fromhex(encoded.decode('ascii'))
        parent = next((i for i, r in reversed(list(enumerate(results)))
                       if r['start'] < group['start'] and r['end'] > group['end']), None)
        results.append({'ordinal': len(results), 'kind': group['kind'],
                        'start': group['start'], 'end': group['end'], 'parent_ordinal': parent,
                        'format': fmt, 'raw_group': data,
                        'raw_group_sha256': hashlib.sha256(data).hexdigest(),
                        'payload': payload,
                        'payload_sha256': hashlib.sha256(payload).hexdigest() if payload else None,
                        'status': 'payload_extracted_unverified' if payload else 'raw_group_preserved'})
    return results
