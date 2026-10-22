"""Record reproducible live HTTP checks; does not change verification labels."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('book_id')
    parser.add_argument('query')
    parser.add_argument('--port',type=int,default=18866)
    args=parser.parse_args()
    base=f'http://127.0.0.1:{args.port}'
    def get(path):
        with urlopen(base+path,timeout=20) as response:
            return json.load(response)
    health=get('/health')
    result=get('/search?'+urlencode({'q':args.query,'book_id':args.book_id}))
    if not result['items']:
        raise SystemExit('No matching decoded paragraph; check actual original characters')
    first=result['items'][0]
    chapter=get('/chapters/'+first['chapter_id'])
    assert args.query in first['original_text']
    assert first['original_text'] in chapter['original_text']
    assert first['source_sha256']==chapter['source_sha256']
    report={'health':health,'query':args.query,'book_id':args.book_id,'first_match':first,
            'chapter_original_length':len(chapter['original_text']),
            'note':'HTTP original-text consistency check only; not a historical or full-chapter collation'}
    output=Path(__file__).resolve().parent/'.local'/f'integration-{args.book_id}.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'book_id':args.book_id,'chapter_id':first['chapter_id'],
                      'match_offsets':first['match_offsets'],'chapter_original_length':report['chapter_original_length'],
                      'report':str(output)},ensure_ascii=False))

if __name__=='__main__':main()
