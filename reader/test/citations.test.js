import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {localSourceLink, resolveDocPath} from '../src/citations.js'
import {JSDOM} from 'jsdom'
import createDOMPurify from 'dompurify'
import {Marked} from 'marked'
import markedFootnote from 'marked-footnote'
import {cleanReaderHtml} from '../src/reader-sanitize.js'
import {filterCases,mountCaseHub} from '../src/case-hub.js'
import {resolveReaderRoute,findReaderAnchor,scrollReaderAnchor} from '../src/reader-route.js'
const sources = JSON.parse(fs.readFileSync(new URL('../sources.json', import.meta.url)))

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
  const md = fs.readFileSync(new URL('../../docs/cases/tang-xuanzong/reader/阅读入口.md', import.meta.url), 'utf8')
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
  assert.equal(filterCases(cases,{year:'849',period:'晚唐'}).length,1)
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
