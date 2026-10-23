import test from 'node:test'
import assert from 'node:assert/strict'
import {JSDOM} from 'jsdom'
import fs from 'node:fs'
import {renderChapterText,mountTextReader} from '../src/text-reader.js'

test('corpus text is rendered literally and query highlighting cannot inject HTML',()=>{
  const window=new JSDOM('<pre></pre>').window
  const root=window.document.querySelector('pre')
  const text='<img src=x onerror="bad()">庞勋与庞勋'
  renderChapterText(root,text,'庞勋')
  assert.equal(root.textContent,text)
  assert.equal(root.querySelectorAll('img,script').length,0)
  assert.equal(root.querySelectorAll('mark').length,2)
  renderChapterText(root,null)
  assert.equal(root.textContent,'原记录无正文。')
  window.close()
})

test('original text and highlights keep high contrast with the Markdown engine styles loaded',()=>{
  const engine=fs.readFileSync(new URL('../src/style.css',import.meta.url),'utf8')
  const local=fs.readFileSync(new URL('../src/local-reader.css',import.meta.url),'utf8')
  const html=fs.readFileSync(new URL('../local.html',import.meta.url),'utf8')
  const window=new JSDOM(html).window
  for(const css of [engine,local]){const style=window.document.createElement('style');style.textContent=css;window.document.head.append(style)}
  const body=window.document.getElementById('text-body')
  renderChapterText(body,'原文阅读高亮','高亮')
  const luminance=color=>color.match(/[\d.]+/g).slice(0,3).map(Number)
    .map(n=>{n/=255;return n<=0.04045?n/12.92:((n+0.055)/1.055)**2.4})
    .reduce((sum,n,i)=>sum+n*[0.2126,0.7152,0.0722][i],0)
  for(const el of [body,body.querySelector('mark')]){
    const style=window.getComputedStyle(el),fg=luminance(style.color),bg=luminance(style.backgroundColor)
    const contrast=(Math.max(fg,bg)+0.05)/(Math.min(fg,bg)+0.05)
    assert.ok(contrast>=7,`Readable contrast required; got ${contrast}`)
  }
  assert.notEqual(body.tagName,'PRE')
  window.close()
})

test('source opens full text, toggles verified reading, lists assets, and searches by selected book',async()=>{
  const html=fs.readFileSync(new URL('../local.html',import.meta.url),'utf8')
  const window=new JSDOM(html).window
  const previous={document:globalThis.document,Option:globalThis.Option}
  globalThis.document=window.document;globalThis.Option=window.Option
  const dialog=document.getElementById('text-dialog')
  dialog.showModal=()=>{dialog.open=true}
  const calls=[]
  async function request(path){
    calls.push(path)
    if(path.startsWith('/api/text/books?'))return [{book_id:'SYNTHETIC',title:'合成书目'}]
    if(path==='/api/text/source/S')return {bookId:'SYNTHETIC',chapterId:'SYNTHETIC:0'}
    if(path.endsWith('/characters'))return {reading_text:'甲龻乙',replacements_applied:1,unresolved_occurrences:0,
      notes:[{offset:1,codepoint:'U+E864',replacement:'龻',font_trace:{font_description:'宋体'}}]}
    if(path.endsWith('/assets'))return {items:[{ordinal:0,kind:'pict',format:'jpegblip',start_byte:10,end_byte:80,payload_size:10}]}
    if(path.startsWith('/api/text/chapters/'))return {chapter_id:'SYNTHETIC:0',book_title:'合成书目',display_title:'合成章',
      original_text:'甲\ue864乙',decoder:'synthetic',verification_status:'decoded_unverified',source_sha256:'0'.repeat(64)}
    if(path.startsWith('/api/text/search?'))return {items:[{chapter_id:'SYNTHETIC:0',book_title:'合成书目',display_title:'合成章',ordinal:0,original_text:'甲乙'}],has_more:false}
    throw new Error('Unexpected endpoint '+path)
  }
  try{
    const reader=mountTextReader(request)
    await reader.source('S','甲')
    assert.equal(dialog.open,true)
    assert.equal(document.getElementById('text-book').value,'SYNTHETIC')
    assert.equal(document.getElementById('text-body').textContent,'甲\ue864乙')
    const toggle=document.getElementById('text-reading')
    assert.equal(toggle.disabled,false)
    toggle.checked=true;toggle.dispatchEvent(new window.Event('change'))
    assert.equal(document.getElementById('text-body').textContent,'甲龻乙')
    assert.equal(document.querySelectorAll('#text-assets a[download]').length,2)
    assert.match(document.querySelector('#text-assets a').getAttribute('href'),/^\/api\/text\/chapters\/SYNTHETIC%3A0\/assets\/0\/download\?part=raw$/)
    document.getElementById('text-form').dispatchEvent(new window.Event('submit',{cancelable:true}))
    await new Promise(resolve=>setImmediate(resolve))
    assert.ok(calls.some(path=>path.includes('/search?')&&path.includes('book_id=SYNTHETIC')))
    assert.equal(document.querySelectorAll('#text-results article').length,1)
    assert.equal(document.getElementById('text-body').textContent,'')
  }finally{globalThis.document=previous.document;globalThis.Option=previous.Option;window.close()}
})
