"""Strict RTF-to-Unicode conversion, including CP936 mixed literal trails."""
import re
import codecs
from contextvars import ContextVar
from striprtf.striprtf import rtf_to_text

RECOVERIES = ContextVar('hanji_gbk_extensions', default=None)


def gbk_extension(error):
    """Decode only valid two-byte GB18030 extensions rejected by Python GBK."""
    if not isinstance(error, UnicodeDecodeError) or error.encoding not in ('gbk', 'cp936'):
        raise error
    pair = error.object[error.start:error.start+2]
    if len(pair) != 2: raise error
    try:
        character = pair.decode('gb18030', errors='strict')
    except UnicodeDecodeError:
        raise error
    if len(character) != 1: raise error
    recoveries = RECOVERIES.get()
    if recoveries is not None: recoveries.append((pair.hex(), ord(character)))
    return character, error.start+2


codecs.register_error('hanji_gbk_extension', gbk_extension)

TOKENS = re.compile(r"\\'[0-9a-fA-F]{2}|\\[a-zA-Z]+-?\d* ?|\\[^a-zA-Z]|[{}]|[^\\{}]+")


def canonicalize_literals(source):
    """Keep RTF syntax, hex-escape byte literals so GBK pairs stay together.

    The old writer emits e.g. \\'b5y: one hex lead byte and a literal ASCII
    trail. striprtf otherwise decodes the lead too early and corrupts a glyph.
    """
    output = []
    for token in TOKENS.findall(source):
        if token in (r'\{', r'\}', r'\\'):
            output.append("\\'%02x" % ord(token[-1]))
        elif token.startswith('\\') or token in ('{','}'):
            output.append(token)
        else:
            # Keep the font-table delimiter visible to striprtf's font parser.
            # ';' cannot be a CP936 trail byte, so it is safe to flush here.
            output.append(''.join(c if c == ';' else "\\'%02x" % ord(c)
                                  for c in token if c not in '\r\n'))
    return ''.join(output)


def decode_rtf(raw):
    if not raw.startswith(b'{\\rtf'):
        raise ValueError('Not an RTF article')
    source = raw.decode('latin-1')
    if re.search(r'\\bin\d+',source):
        raise ValueError('Binary RTF payload requires separate parser; article quarantined')
    if re.search(r'\\(?:footnote|annotation|header[lrf]?|footer[lrf]?)\b',source):
        raise ValueError('Non-body RTF text requires separate preservation; article quarantined')
    for codepage in re.findall(r'\\ansicpg(\d+)',source):
        codecs.lookup('cp'+codepage)  # Do not allow striprtf's unknown-codepage fallback.
    tokens = TOKENS.findall(source)
    depth = 0
    for token in tokens:
        if token == '{': depth += 1
        elif token == '}': depth -= 1
        if depth < 0: raise ValueError('Unbalanced RTF groups')
    if depth: raise ValueError('Truncated RTF groups')
    recoveries = []
    context = RECOVERIES.set(recoveries)
    try:
        text = rtf_to_text(canonicalize_literals(source),encoding='cp936',errors='hanji_gbk_extension')
    finally:
        RECOVERIES.reset(context)
    if '\ufffd' in text: raise ValueError('Replacement characters in decoded article')
    if any(0xd800 <= ord(c) <= 0xdfff for c in text):
        text = text.encode('utf-16-le',errors='surrogatepass').decode('utf-16-le',errors='strict')
    metadata = {'rtf_codepage': re.findall(r'\\ansicpg(\d+)',source),
                'embedded_object_count':len(re.findall(r'\\(?:pict|object)\b',source)),
                'replacement_count':text.count('\ufffd'),
                'gb18030_extension_count':len(recoveries),
                'gb18030_extensions':[{'bytes':rawhex,'unicode':f'U+{code:04X}'}
                                      for rawhex,code in sorted(set(recoveries))],
                'private_use_count':sum(0xe000 <= ord(c) <= 0xf8ff or
                                        0xf0000 <= ord(c) <= 0xffffd or
                                        0x100000 <= ord(c) <= 0x10fffd for c in text),
                'conversion':'strict-byte-canonicalization+striprtf'}
    return text,metadata
