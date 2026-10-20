"""One-time, non-overwriting import of the existing example manuscripts."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / 'docs' / 'cases' / 'tang-xuanzong'

def main():
    for folder in ('年事', '纪传体', '古地理与行政区划', '唐宣宗_846—859', 'reader'):
        for source in (ROOT / folder).glob('*.md'):
            if folder == 'reader' and source.name not in ('阅读入口.md', '本机阅读器说明.md', '自动定位实机验收.md'):
                continue
            target = CASE / folder / source.name
            if target.exists(): continue
            target.parent.mkdir(parents=True, exist_ok=True)
            text = source.read_text(encoding='utf-8')
            if folder == '年事':
                text = re.sub(r'(?m)^(## .*?[（(](8\d\d)[）)].*)$',
                    lambda m: f'<a id="year-{m[2]}"></a>\n\n{m[1]}', text)
            target.write_text(text, encoding='utf-8')
    prefix = CASE.relative_to(ROOT).as_posix()
    entry = f'{prefix}/reader/阅读入口.md'
    chronology = f'{prefix}/年事/唐宣宗_年事初表.md'
    documents = [p.relative_to(ROOT).as_posix() for p in sorted(CASE.rglob('*.md'))]
    case = dict(id='tang-xuanzong',title='唐宣宗：编年、人物与历史地理',period='晚唐',
        startYear=846,endYear=859,status='研究初稿',
        description='以两《唐书》和《资治通鉴》为主干，从编年、纪传、地理及社会生活互相参照。',
        topics=['牛李党争','方镇','多民族交往','制度经济','饮食酒茶'],
        entry=entry,documents=documents,
        sections=[dict(id=str(a),title=title,startYear=a,endYear=b,description=desc)
            for a,b,title,desc in [(846,850,'即位与河陇经营','人事更替、三州七关收复及经营措施'),
                (851,855,'归义军与中期政局','沙州归附、地方治理及灾荒'),
                (856,859,'晚期政局与继承','方镇军情、宦官与皇位继承')]],
        years=[dict(year=y,label='会昌六年' if y==846 else ('大中元年' if y==847 else '大中'+
                    {2:'二',3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三'}[y-846]+'年'),
                    doc=chronology,anchor=f'year-{y}') for y in range(846,860)])
    manifest = ROOT / 'docs' / 'cases.json'
    if not manifest.exists():
        manifest.write_text(json.dumps({'cases':[case]}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Imported {len(documents)} manuscripts without overwriting existing docs.')

if __name__ == '__main__': main()
