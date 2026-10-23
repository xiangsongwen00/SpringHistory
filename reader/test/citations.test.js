import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {localSourceLink, resolveDocPath, resolveDocumentLink} from '../src/citations.js'
import {relatedTopicLinks,mountTopicLinks} from '../src/topic-navigation.js'
import {JSDOM} from 'jsdom'
import createDOMPurify from 'dompurify'
import {Marked} from 'marked'
import markedFootnote from 'marked-footnote'
import {cleanReaderHtml} from '../src/reader-sanitize.js'
import {filterCases,mountCaseHub} from '../src/case-hub.js'
import {resolveReaderRoute,findReaderAnchor,scrollReaderAnchor} from '../src/reader-route.js'
const sources = JSON.parse(fs.readFileSync(new URL('../sources.json', import.meta.url)))

test('all eleven topics navigate between background and three reigns, including target anchors',()=>{
  const cases=JSON.parse(fs.readFileSync(new URL('../../docs/cases.json',import.meta.url))).cases
  const bg=cases.find(c=>c.id==='late-tang-background')
  const topics=bg.documents.filter(p=>fs.readFileSync(new URL('../../'+p,import.meta.url),'utf8').includes('id="background-mechanism"'))
  assert.equal(topics.length,11)
  assert.deepEqual(relatedTopicLinks(bg.documents.find(p=>p.endsWith('/学术研究述评与论文导航.md')),cases),[])
  const window=new JSDOM('<article><h1>专题</h1></article>').window
  const root=window.document.querySelector('article')
  const parser=new Marked(markedFootnote())
  for(const path of topics){
    const links=relatedTopicLinks(path,cases)
    assert.equal(links.length,4)
    for(const link of links){
      const current=relatedTopicLinks(link.path,cases)
      assert.equal(current.filter(l=>l.current).length,1)
      let opened
      mountTopicLinks(root,current,(c,p)=>{opened={c,p}})
      assert.equal(root.querySelectorAll('.topic-navigation').length,1)
      assert.equal(root.querySelector('[aria-current]').textContent,link.label)
      root.querySelectorAll('.topic-navigation a')[link.current?1:0].click()
      assert.ok(opened)
      assert.ok(opened.c.documents.includes(opened.p))
      root.innerHTML=parser.parse(fs.readFileSync(new URL('../../'+link.path,import.meta.url),'utf8'))
      const cross=[...root.querySelectorAll('a[href]')].map(a=>resolveDocumentLink(link.path,a.getAttribute('href'),cases,link.case.id)).filter(t=>t&&t.case.id!==link.case.id&&t.hash)
      assert.ok(cross.length>0,link.path+' has cross-case anchor')
      for(const t of cross){
        const destination=new JSDOM(parser.parse(fs.readFileSync(new URL('../../'+t.path,import.meta.url),'utf8')))
        assert.ok(destination.window.document.getElementById(t.hash),t.path+'#'+t.hash)
        const route=resolveReaderRoute('#'+new URLSearchParams({case:t.case.id,doc:t.path,anchor:t.hash}),cases)
        assert.equal(route.case.id,t.case.id)
        destination.window.close()
      }
    }
  }
  assert.equal(resolveDocumentLink(topics[0],'https://example.com',cases,bg.id),null)
  assert.equal(resolveDocumentLink(topics[0],'../../../unregistered.md',cases,bg.id),null)
  window.close()
})

test('migrated case bookmarks retain document and anchor; grouped navigation opens the same article', () => {
  const cases=JSON.parse(fs.readFileSync(new URL('../../docs/cases.json',import.meta.url))).cases
  const window=new JSDOM('<div id="case-grid"></div><div id="case-detail"></div><input id="case-search"><select id="case-period"></select><input id="case-year"><div id="case-count"></div>').window
  const prior=globalThis.document
  globalThis.document=window.document
  try {
    let opened
    const hub=mountCaseHub(cases,(...args)=>{opened=args})
    for(const c of cases.filter(c=>c.layoutVersion)){
      hub.showCase(c)
      assert.ok([...window.document.querySelectorAll('#case-detail h4')].some(h=>h.textContent==='文化制度以及影响研究'))
      const group=c.documentGroups.find(g=>g.title==='文化制度以及影响研究')
      assert.equal(group.documents.length,11)
      const button=[...window.document.querySelectorAll('#case-detail button')].find(b=>b.textContent==='宦官与监军')
      button.click()
      assert.deepEqual(opened.slice(0,2),[c,group.documents.find(p=>p.endsWith('/宦官与监军.md'))])
      for(const [old,path] of Object.entries(c.legacyPaths)){
        const route=resolveReaderRoute('#'+new URLSearchParams({case:c.id,doc:old,anchor:'year-859'}),cases,[])
        assert.equal(route.path,path)
        assert.equal(route.anchor,'year-859')
      }
      assert.equal(resolveReaderRoute('#'+new URLSearchParams({case:c.id,doc:'../../secret.md'}),cases,[]),null)
    }
    for(const c of cases.filter(c=>!c.layoutVersion)){
      hub.showCase(c)
      assert.equal(window.document.querySelectorAll('.year-grid, .stage-bar').length,0)
      assert.ok(window.document.querySelectorAll('.document-grid button').length>0)
    }
  } finally {globalThis.document=prior;window.close()}
})

test('old salt-tea footnote URL resolves to its actual article instead of the hub', () => {
  const cases = JSON.parse(fs.readFileSync(new URL('../../docs/cases.json', import.meta.url))).cases
  const docs = cases.flatMap(c=>c.documents.map(path=>({path,
    content:fs.readFileSync(new URL('../../'+path,import.meta.url),'utf8')})))
  const route = resolveReaderRoute('#footnote-ref-%E7%9B%90%E8%8C%B6',cases,docs)
  assert.equal(route.case.id,'tang-xuanzong')
  assert.equal(route.path,cases[0].entry)
  assert.equal(route.anchor,'footnote-ref-盐茶')
  assert.equal(resolveReaderRoute('#footnote-ref-%FF',cases,docs),null)
  assert.equal(resolveReaderRoute('#footnote-ref-盐茶',cases,[...docs,docs.find(d=>d.path===route.path)]),null)
})

test('Chinese footnotes resolve literal encoded IDs and scroll the article container', () => {
  const window = new JSDOM('<div id="content"><p id="footnote-ref-%E7%9B%90%E8%8C%B6">ref</p><p id="footnote-%E7%9B%90%E8%8C%B6">note</p></div>').window
  const doc = window.document
  assert.equal(findReaderAnchor(doc,'footnote-ref-盐茶').textContent,'ref')
  assert.equal(findReaderAnchor(doc,'#footnote-%E7%9B%90%E8%8C%B6').textContent,'note')
  const content = doc.getElementById('content')
  content.getBoundingClientRect = ()=>({top:62})
  findReaderAnchor(doc,'footnote-盐茶').getBoundingClientRect = ()=>({top:520})
  let options
  content.scrollTo = value=>{options=value}
  assert.equal(scrollReaderAnchor(doc,'#footnote-%E7%9B%90%E8%8C%B6'),true)
  assert.equal(options.top,434)
  assert.equal(scrollReaderAnchor(doc,'missing'),false)
  window.close()
})

test('native references preserve queries and Chinese ID suffixes', () => {
  assert.deepEqual(localSourceLink('hanji://J18?q=大中', sources), {id:'J18',query:'大中'})
  assert.deepEqual(localSourceLink('hanji://J190下', sources), {id:'J190下',query:null})
  assert.equal(localSourceLink('hanji://unknown', sources), null)
})
test('public source URLs map to exact registered local volumes', () => {
  assert.equal(localSourceLink('https://zh.wikisource.org/wiki/舊唐書/卷18下',sources).id, 'J18')
  assert.equal(localSourceLink('https://zh.wikisource.org/zh-hant/新唐書/卷054',sources).id, 'X54')
  assert.equal(localSourceLink('https://example.org/新唐書/卷054',sources), null)
})
test('relative Markdown navigation keeps Chinese paths', () => {
  assert.deepEqual(resolveDocPath('reader/阅读入口.md', '../年事/唐宣宗_年事初表.md'),
    {path:'年事/唐宣宗_年事初表.md',hash:''})
})

test('real reading entry renders reciprocal footnotes and preserves local citations', () => {
  const window = new JSDOM('').window
  const parser = new Marked(markedFootnote())
  const md = fs.readFileSync(new URL('../../docs/cases/tang-xuanzong/阅读入口.md', import.meta.url), 'utf8')
  window.document.body.innerHTML = cleanReaderHtml(createDOMPurify(window), parser.parse(md))
  const refs = [...window.document.querySelectorAll('a[data-footnote-ref]')]
  assert.equal(refs.length, 2)
  for (const ref of refs) {
    const target = window.document.getElementById(ref.hash.slice(1))
    assert.ok(target, 'footnote target exists')
    const back = target.querySelector('a[data-footnote-backref]')
    assert.ok(back)
    assert.ok(window.document.getElementById(back.hash.slice(1)))
  }
  assert.equal(window.document.querySelectorAll('a[href^="hanji:"]').length, 2)
  window.close()
})

test('reader rejects executable HTML and foreign launch protocols', () => {
  const window = new JSDOM('').window
  const dirty = '<script>alert(1)</script><img src=x onerror="alert(1)"><iframe src=x></iframe>' +
    '<a href="javascript:alert(1)">js</a><a href="file:///C:/secret">file</a>' +
    '<a href="powershell:bad">shell</a><a href="hanji://J18">source</a>'
  window.document.body.innerHTML = cleanReaderHtml(createDOMPurify(window), dirty)
  assert.equal(window.document.querySelectorAll('script,iframe,[onerror]').length, 0)
  assert.deepEqual([...window.document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')), ['hanji://J18'])
  window.close()
})

test('case hub filters periods and years, then opens the selected year anchor', () => {
  const cases = JSON.parse(fs.readFileSync(new URL('../../docs/cases.json', import.meta.url))).cases
  assert.deepEqual(filterCases(cases,{year:'849',period:'晚唐'}).map(c=>c.id),['tang-xuanzong','late-tang-background'])
  assert.equal(filterCases(cases,{year:'900'}).length,0)
  const window = new JSDOM('<input id="case-search"><select id="case-period"><option value=""></option></select><input id="case-year"><p id="case-count"></p><div id="case-grid"></div><section id="case-detail" hidden></section>').window
  const previous = globalThis.document
  globalThis.document = window.document
  try {
    const opened = []
    mountCaseHub(cases,(c,path,anchor)=>opened.push({id:c.id,path,anchor}))
    document.querySelector('#case-grid button').click()
    assert.equal(document.querySelectorAll('.year-grid button').length,14)
    document.querySelectorAll('.stage-bar button')[2].click()
    assert.equal(document.querySelectorAll('.year-grid button').length,5)
    document.querySelector('.year-grid button').click()
    assert.equal(opened[0].anchor,'year-851')
    const md = fs.readFileSync(new URL('../../'+opened[0].path, import.meta.url),'utf8')
    assert.ok(md.includes('id="year-851"'))
    assert.ok(opened[0].path.startsWith('docs/'))
  } finally { globalThis.document = previous; window.close() }
})

test('new reign cases have complete year navigation and resolvable footnote sources',()=>{
  const cases=JSON.parse(fs.readFileSync(new URL('../../docs/cases.json',import.meta.url))).cases
  assert.deepEqual(filterCases(cases,{year:'873'}).filter(c=>c.layoutVersion).map(c=>c.id),['tang-yizong','tang-xizong'])
  const window=new JSDOM('').window
  const parser=new Marked(markedFootnote())
  for(const [id,years] of [['tang-yizong',15],['tang-xizong',16]]){
    const c=cases.find(c=>c.id===id)
    assert.equal(c.years.length,years)
    for(const y of c.years){
      const md=fs.readFileSync(new URL('../../'+y.doc,import.meta.url),'utf8')
      assert.ok(md.includes(`id="${y.anchor}"`))
    }
    for(const path of c.documents){
      const md=fs.readFileSync(new URL('../../'+path,import.meta.url),'utf8')
      window.document.body.innerHTML=cleanReaderHtml(createDOMPurify(window),parser.parse(md))
      for(const a of window.document.querySelectorAll('a[href^="hanji:"]')){
        assert.ok(localSourceLink(a.getAttribute('href'),sources),path+' has registered source')
      }
      for(const a of window.document.querySelectorAll('a[data-footnote-ref]')){
        assert.ok(window.document.getElementById(a.hash.slice(1)),path+' has footnote target')
      }
    }
  }
  window.close()
})
