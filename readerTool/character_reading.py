"""Reversible character reading layer. Archival text is never rewritten."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
MAP=json.loads((HERE/'gb18030_legacy_map.json').read_text(encoding='utf8'))
MAPPINGS={r['source']:r for r in MAP['mappings']}


def safe_mapping(note):
    entry=MAPPINGS.get(note['codepoint'])
    font=note.get('font_trace') or {}
    description=font.get('font_description','')
    family=re.sub(r'^[0-9a-fA-F]{20}(?=\D)', '', description).strip().lstrip('@').casefold()
    if (not entry or font.get('custom_font') or
            family not in ('宋体','simsun') or
            font.get('legacy_bytes')!=entry['bytes']):
        return None
    return entry


def reading_view(chapter,record):
    text=chapter.get('original_text')
    if text is None:
        return {'status':'no_body','original_text':None,'reading_text':None,'notes':[],
                'replacements_applied':0,'original_unchanged':True}
    if record is None:
        return {'status':'no_character_record','original_text':text,'reading_text':text,
                'notes':[],'replacements_applied':0,'original_unchanged':True}
    expected=hashlib.sha256(text.encode('utf8')).hexdigest()
    if (record['chapter_id']!=chapter['chapter_id'] or record['text_sha256']!=expected or
            record['source_sha256']!=chapter['source_sha256'] or record['decoder']!=chapter['decoder']):
        raise ValueError('Character notes do not match current chapter text/provenance; regenerate the notes')
    chars=list(text);count=0;notes=[];seen=set()
    for source in record['notes']:
        note=dict(source);offset=note['offset']
        if offset in seen or not 0<=offset<len(chars) or f'U+{ord(text[offset]):04X}'!=note['codepoint']:
            raise ValueError('Character note offset/codepoint mismatch')
        seen.add(offset)
        entry=safe_mapping(note)
        if entry:
            chars[offset]=entry['character'];count+=1
            note.update(status='encoding_mapping_verified',replacement=entry['character'],
                        target_codepoint=entry['target'],mapping_version=MAP['version'],
                        mapping_source=MAP['source_url'],mapping_source_sha256=MAP['source_sha256'])
        else:
            note.update(status='custom_font_missing' if (note.get('font_trace') or {}).get('custom_font')
                        else 'unresolved',replacement=None)
        notes.append(note)
    return {'status':'character_notes_available','original_text':text,'reading_text':''.join(chars),
            'notes':notes,'replacements_applied':count,'unresolved_occurrences':len(notes)-count,
            'original_unchanged':True,'mapping_version':MAP['version'],
            'verification_note':'Encoding modernization only. Historical verification status is unchanged.'}
