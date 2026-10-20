import { marked } from 'marked'
import markedFootnote from 'marked-footnote'
import DOMPurify from 'dompurify'
import { cleanReaderHtml } from './reader-sanitize.js'
import { mountCaseHub } from './case-hub.js'
import { resolveReaderRoute, scrollReaderAnchor } from './reader-route.js'
import { createMarkdownEngine } from './index.js'
import { localSourceLink, resolveDocPath } from './citations.js'
import './local-reader.css'

marked.use(markedFootnote())
const $ = id => document.getElementById(id)
let engine, boot, currentCase, pendingAnchor, activeSource, opening = false

function showHub() {
  document.body.dataset.view = 'hub'
  $('case-hub').hidden = false; $('app').hidden = true
  $('research-context').textContent = '选择研究案例'
  document.title = '史地阅读室 · 研究案例'
}

function readDoc(c, path, anchor='') {
  if (!c.documents.includes(path)) return
  currentCase = c
  document.body.dataset.view = 'reading'
  pendingAnchor = anchor
  $('case-hub').hidden = true; $('app').hidden = false
  $('research-context').textContent = c.title
  document.title = `${c.title} · 史地阅读室`
  const docs = boot.docs.filter(d=>c.documents.includes(d.path))
  if (!engine) engine = createMarkdownEngine({container:'#app',docs,defaultDocId:path,sanitizeHtml:cleanHtml})
  else engine.setDocs(docs,path)
}

function goRead(c,path,anchor='') {
  const route = new URLSearchParams({case:c.id,doc:path})
  if (anchor) route.set('anchor',anchor)
  const hash = `#${route}`
  if (location.hash === hash) readDoc(c,path,anchor)
  else location.hash = hash
}

function route() {
  const resolved = resolveReaderRoute(location.hash,boot.cases,boot.docs)
  if (resolved) {
    const {case:c,path,anchor} = resolved
    history.replaceState(null,'',`#${new URLSearchParams({case:c.id,doc:path,...(anchor ? {anchor} : {})})}`)
    readDoc(c,path,anchor)
  }
  else showHub()
}

async function request(path, options) {
  const response = await fetch(path, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || '本机服务返回错误')
  return data
}

function cleanHtml(html) {
  return cleanReaderHtml(DOMPurify, html)
}

document.addEventListener('markdown-rendered', event => {
  if (currentCase && event.detail?.path && event.detail.path !== new URLSearchParams(location.hash.slice(1)).get('doc')) {
    history.replaceState(null,'',`#${new URLSearchParams({case:currentCase.id,doc:event.detail.path})}`)
  }
  if (pendingAnchor) {
    const anchor = pendingAnchor; pendingAnchor = ''
    requestAnimationFrame(()=>scrollReaderAnchor(document,anchor))
  }
  const content = $('content')
  if (!content || !boot) return
  const ids = Object.keys(boot.sources).sort((a, b) => b.length - a.length)
  const pattern = new RegExp(`(?<![A-Za-z0-9])(${ids.join('|')})(?![A-Za-z0-9])`, 'g')
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT)
  const nodes = []
  while (walker.nextNode()) {
    const node = walker.currentNode
    if (!node.parentElement.closest('a,code,pre,script,button,textarea') &&
        node.textContent.match(pattern)) nodes.push(node)
  }
  for (const node of nodes) {
    const fragment = document.createDocumentFragment()
    let start = 0
    for (const match of node.textContent.matchAll(pattern)) {
      fragment.append(node.textContent.slice(start, match.index))
      const anchor = document.createElement('a')
      anchor.href = `hanji://${match[1]}`
      anchor.className = 'hanji-ref'
      anchor.textContent = match[1]
      anchor.title = `${boot.sources[match[1]].label} · 查本机`
      fragment.append(anchor)
      start = match.index + match[0].length
    }
    fragment.append(node.textContent.slice(start))
    node.replaceWith(fragment)
  }
  // Keep remote transcription links; add a separate native shortcut alongside.
  for (const anchor of content.querySelectorAll('a[href]')) {
    const href = anchor.getAttribute('href')
    const link = localSourceLink(href, boot.sources)
    if (!link || href.startsWith('hanji:')) continue
    const local = document.createElement('a')
    local.href = `hanji://${link.id}`
    local.className = 'hanji-ref local-shortcut'
    local.textContent = '查本机'
    anchor.after(local)
  }
})

async function showSource(id, query) {
  $('job-status').textContent = ''
  $('source-label').textContent = boot.sources[id]?.label || id
  $('source-detail').replaceChildren()
  $('source-evidence').textContent = '正在核对本机书目和卷章…'
  $('query-word').value = query ?? boot.sources[id]?.query ?? ''
  activeSource = null
  $('open-auto').disabled = $('open-book').disabled = true
  if (!$('source-dialog').open) $('source-dialog').showModal()
  try {
    const source = await request(`/api/source/${encodeURIComponent(id)}`)
    activeSource = source
    $('source-evidence').textContent = '已在本机目录确认书与卷章 · 引文尚待正文校勘'
    for (const [key, value] of [['书名', source.book], ['卷章标题', source.chapter],
      ['书库编号', source.bookId], ['定位状态', '目录已核；已实测卷次和检索词见阅读器使用说明']]) {
      const dt = document.createElement('dt'), dd = document.createElement('dd')
      dt.textContent = key; dd.textContent = value
      $('source-detail').append(dt, dd)
    }
    $('open-auto').disabled = !boot.driverInstalled || !boot.exeExists
    $('open-book').disabled = !boot.exeExists
  } catch (error) { $('source-evidence').textContent = error.message }
}

document.addEventListener('click', event => {
  const anchor = event.target.closest('a[href]')
  if (!anchor || !boot) return
  if (anchor.id === 'home') {
    event.preventDefault(); location.hash = ''; showHub(); return
  }
  const href = anchor.getAttribute('href')
  const local = localSourceLink(href, boot.sources)
  if (href.startsWith('hanji:')) {
    event.preventDefault()
    if (local) showSource(local.id, local.query)
    return
  }
  if (href.startsWith('#')) {
    event.preventDefault()
    scrollReaderAnchor(document,href)
    return
  }
  if (!/^[a-z][a-z0-9+.-]*:/i.test(href)) {
    if (!engine || !currentCase) return
    const target = resolveDocPath(engine.getCurrentDoc().path, href)
    if (engine.getDocs().some(d => d.path === target.path)) {
      event.preventDefault(); goRead(currentCase,target.path,target.hash)
      return
    }
    event.preventDefault()
    return
  }
  // A document must never execute arbitrary custom protocols or local files.
  if (!/^https?:|^mailto:/i.test(href)) event.preventDefault()
})

for (const dialog of document.querySelectorAll('dialog')) {
  dialog.querySelector('.close').addEventListener('click', () => dialog.close())
}

async function openNative(mode) {
  if (!activeSource || opening) return
  opening = true
  $('open-auto').disabled = $('open-book').disabled = true
  try {
    let job = await request('/api/open', { method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-Reader-Token': boot.token },
      body: JSON.stringify({sourceId: activeSource.id, query: $('query-word').value, mode}) })
    $('job-status').textContent = job.message
    while (job.state === 'running') {
      await new Promise(resolve => setTimeout(resolve, 700))
      job = await request(`/api/job/${job.id}`)
      $('job-status').textContent = job.message
    }
    $('job-status').dataset.state = job.state
  } catch (error) { $('job-status').textContent = error.message }
  finally {
    opening = false
    $('open-auto').disabled = !boot.driverInstalled || !boot.exeExists
    $('open-book').disabled = !boot.exeExists
  }
}
$('open-auto').addEventListener('click', () => openNative('auto'))
$('open-book').addEventListener('click', () => openNative('book'))
$('copy-query').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('query-word').value); $('job-status').textContent = '已复制检索词。' }
  catch { $('query-word').focus(); $('query-word').select(); $('job-status').textContent = '请按 Ctrl+C 复制。' }
})

function renderCatalog() {
  const keyword = $('catalog-search').value.trim()
  const matches = boot.books.filter(b => b.title.includes(keyword))
  $('catalog-count').textContent = `本次识别 ${boot.books.length} 项 · 符合 ${matches.length} 项`
  $('catalog-list').replaceChildren()
  for (const book of matches) {
    const row = document.createElement('details'), summary = document.createElement('summary')
    summary.textContent = `${book.title}　${book.id}　${book.available ? '目录及书库文件存在' : '书库文件缺失'}`
    const body = document.createElement('div')
    body.className = 'chapter-list'
    body.textContent = '展开后读取本机篇章标题（不导出正文）。'
    row.append(summary, body)
    row.addEventListener('toggle', async () => {
      if (!row.open || row.dataset.loaded) return
      row.dataset.loaded = 'yes'
      try {
        const chapters = await request(`/api/chapters/${book.id}`)
        body.replaceChildren()
        for (const c of chapters) {
          const line = document.createElement('p'); line.textContent = c.title; body.append(line)
        }
        if (!chapters.length) body.textContent = '未能解析篇章标题，请在原系统内查看。'
      } catch (e) { body.textContent = e.message }
    })
    $('catalog-list').append(row)
  }
}
$('library-button').addEventListener('click', () => { renderCatalog(); $('catalog-dialog').showModal() })
$('catalog-search').addEventListener('input', renderCatalog)

try {
  boot = await request('/api/bootstrap')
  $('bridge-health').textContent = boot.exeExists ? '本机资料已连接' : '未找到汉籍程序'
  mountCaseHub(boot.cases,goRead)
  window.addEventListener('hashchange',route)
  route()
} catch (error) {
  $('bridge-health').textContent = '本机服务连接失败'
  $('app').textContent = error.message
}
