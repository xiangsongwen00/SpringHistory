/*
 * @File: src/main.js
 * @Description: 渲染 Markdown 文档，生成目录并提供导出功能
 * @Author: 2409479323@qq.com
 * @LastUpdated: 2026-02-06
 */

import { marked } from 'marked'
import mermaid from 'mermaid'
import { fillAllMermaidToCanvas, fitAllMermaidToDiagram, initMermaidZoom, refreshAllMermaidOverlays } from './mermaidZoom.js'

const engineState = {
  container: null,
  markdownDocs: [],
  currentDoc: null,
  sanitizeHtml: html => html,
  renderToken: 0
}

let mermaidInitialized = false

function escapeMarkup(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]))
}

export function createMarkdownDocsFromModules(modules) {
  return buildMarkdownDocs(modules)
}

export function createMarkdownEngine(options = {}) {
  const {
    container = '#app',
    docs = [],
    defaultDocId = ''
  } = options

  const containerElement =
    typeof container === 'string' ? document.querySelector(container) : container

  if (!containerElement) {
    throw new Error(`Markdown 引擎初始化失败，未找到容器: ${String(container)}`)
  }

  engineState.container = containerElement
  engineState.sanitizeHtml = options.sanitizeHtml || (html => html)
  engineState.markdownDocs = normalizeDocs(docs)
  engineState.currentDoc = selectDefaultDoc(engineState.markdownDocs, defaultDocId)

  if (!mermaidInitialized) {
    mermaid.initialize(DEFAULT_MERMAID_CONFIG)
    mermaidInitialized = true
  }

  renderMarkdown()

  return {
    render: renderMarkdown,
    setDocs(nextDocs, nextDefaultDocId = '') {
      engineState.markdownDocs = normalizeDocs(nextDocs)
      engineState.currentDoc = selectDefaultDoc(engineState.markdownDocs, nextDefaultDocId)
      renderMarkdown()
    },
    renderDocById(docId) {
      const target = engineState.markdownDocs.find(doc => doc.path === docId)
      if (!target) return false
      engineState.currentDoc = target
      renderMarkdown()
      return true
    },
    getDocs() {
      return [...engineState.markdownDocs]
    },
    getCurrentDoc() {
      return engineState.currentDoc
    },
    destroy() {
      engineState.renderToken += 1
      if (engineState.container) {
        engineState.container.innerHTML = ''
      }
      engineState.container = null
      engineState.markdownDocs = []
      engineState.currentDoc = null
    }
  }
}

// 渲染当前文档及目录
function renderMarkdown() {
  const app = engineState.container
  const { markdownDocs, currentDoc } = engineState
  if (!app) return
  const currentRenderToken = ++engineState.renderToken
  console.log('[ReadMarkdownDebug] render start', {
    renderToken: currentRenderToken,
    docsCount: markdownDocs.length,
    currentDoc: currentDoc?.label || currentDoc?.path || null
  })
  app.innerHTML = '<div class="loading">渲染中...</div>'

  if (!currentDoc) {
    app.innerHTML = `
      <div id="sidebar">
        <div class="doc-selector">
          <label for="doc-select">文档</label>
          <select id="doc-select" disabled>
            <option>未找到文档</option>
          </select>
          <div class="doc-actions">
            <button class="export-btn import-doc-btn" data-action="import-docs" type="button">导入新文档</button>
          </div>
        </div>
        <div class="sidebar-header">
          <h2>目录</h2>
          <div class="export-actions">
            <button class="export-btn" data-export="pdf" type="button" disabled>导出 PDF</button>
            <button class="export-btn ghost" data-export="word" type="button" disabled>导出 Word</button>
          </div>
        </div>
        <ul id="toc"></ul>
      </div>
      <div id="content">
        <div class="error">未找到可渲染的 Markdown 文档。</div>
      </div>
    `
    return
  }

  try {
    const markdownContent = currentDoc.content
    const docOptions = markdownDocs
      .map(doc => {
        const selected = doc.path === currentDoc.path ? 'selected' : ''
        return `<option value="${escapeMarkup(doc.path)}" ${selected}>${escapeMarkup(doc.label)}</option>`
      })
      .join('')

    const toc = generateTOC(markdownContent)

    const html = marked(markdownContent)
    
    // 将代码块中的 mermaid 图表包装在 mermaid div 中
    let processedHtml = html.replace(/<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g, 
      '<div class="mermaid">$1</div>')
    
    // 处理视频标签：将 img 标签中 .mp4/.webm/.ogg 后缀的转换为 video 标签
    processedHtml = processedHtml.replace(/<img([^>]*)src=["']([^"']+\.(mp4|webm|ogg))["']([^>]*)\/?>/gi, 
      (match, before, src, ext, after) => {
        // 提取 alt 文本（如果有）
        const altMatch = (before + after).match(/alt=["']([^"']*)["']/i)
        const alt = altMatch ? altMatch[1] : ''
        return `<video controls style="max-width:100%;height:auto;"><source src="${src}" type="video/${ext}">${alt}</video>`
      })

    app.innerHTML = `
      <div id="sidebar">
        <div class="doc-selector">
          <label for="doc-select">文档</label>
          <select id="doc-select">
            ${docOptions}
          </select>
          <div class="doc-actions">
            <button class="export-btn import-doc-btn" data-action="import-docs" type="button">导入新文档</button>
          </div>
        </div>
        <div class="sidebar-header">
          <h2>目录</h2>
          <div class="export-actions">
            <button class="export-btn" data-export="pdf" type="button">导出 PDF</button>
            <button class="export-btn ghost" data-export="word" type="button">导出 Word</button>
          </div>
        </div>
        <ul id="toc">
          ${toc}
        </ul>
      </div>
      <div id="content">
        ${engineState.sanitizeHtml(processedHtml)}
      </div>
    `

    addHeadingIds()
    initExportActions()
    initDocSelector()
    initCodeCopyButtons()
    document.dispatchEvent(new CustomEvent('markdown-rendered', { detail: { path: currentDoc.path } }))
    logComputedThemeSnapshot(currentRenderToken)

    // 渲染 Mermaid 图表
    setTimeout(async () => {
      if (currentRenderToken !== engineState.renderToken) return
      await renderMermaidDiagrams(currentRenderToken)
      if (currentRenderToken !== engineState.renderToken) return
      // Mermaid SVG 就绪后再初始化交互，避免切换文档后控制按钮失效
      await new Promise((resolve) => requestAnimationFrame(resolve))
      if (currentRenderToken !== engineState.renderToken) return
      initMermaidZoom()
    }, 100)
  } catch (error) {
    app.innerHTML = `<div class="error">渲染失败: ${error.message}</div>`
  }
}

const DEFAULT_MERMAID_CONFIG = {
  startOnLoad: false,
  theme: 'default',
  themeVariables: {
    primaryColor: '#3b82f6',      // 蓝色 - 深度1默认色
    primaryTextColor: '#ffffff',
    primaryBorderColor: '#3b82f6',
    secondaryColor: '#e5e7eb',    // 浅灰色 - 深度0
    tertiaryColor: '#06b6d4',     // 青色 - 深度2
    lineColor: '#f9a8d4',         // 淡粉色 - 连接线
    background: '#ffffff',
    textColor: '#1f2937',
    clusterBkg: '#f97316',        // 橙色 - 深度3
    clusterBorder: '#f97316',
    defaultLinkColor: '#f9a8d4',
    // 添加更多层级颜色
    specialColor: '#fbbf24',      // 黄色 - 深度4
    fillType0: '#e5e7eb',         // 深度0
    fillType1: '#3b82f6',         // 深度1
    fillType2: '#06b6d4',         // 深度2
    fillType3: '#f97316',         // 深度3
    fillType4: '#fbbf24',         // 深度4
    fillType5: '#ffffff',         // 深度5
    // 字体大小设置
    fontSize: '16px'
  },
  flowchart: {
    useMaxWidth: false,           // 改为 false，允许图表完整显示
    htmlLabels: true,
    curve: 'basis',
    nodeSpacing: 60,              // 增加节点间距
    rankSpacing: 80,              // 增加层级间距
    padding: 20,                  // 增加内边距
    defaultRenderer: 'dagre'      // 使用 dagre 布局
  },
  securityLevel: 'loose',
  fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
  logLevel: 'debug'
}

function logComputedThemeSnapshot(renderToken) {
  setTimeout(() => {
    if (renderToken !== engineState.renderToken) return
    const content = document.getElementById('content')
    const paragraph = document.querySelector('#content p')
    const pre = document.querySelector('#content pre')
    const styleTag = document.querySelector('style[data-read-markdown-engine="true"]')

    if (!content) {
      console.warn('[ReadMarkdownDebug] theme snapshot skipped: #content missing')
      return
    }

    const contentStyles = getComputedStyle(content)
    const paragraphStyles = paragraph ? getComputedStyle(paragraph) : null
    const preStyles = pre ? getComputedStyle(pre) : null

    console.log('[ReadMarkdownDebug] theme snapshot', {
      renderToken,
      hasEngineStyleTag: Boolean(styleTag),
      contentBackground: contentStyles.background,
      contentColor: contentStyles.color,
      paragraphColor: paragraphStyles?.color || null,
      preBackground: preStyles?.backgroundColor || null,
      preColor: preStyles?.color || null
    })
  }, 0)
}

console.log('Mermaid loaded successfully')

// 渲染 Mermaid 图表
async function renderMermaidDiagrams(renderToken) {
  console.log('开始渲染 Mermaid 图表')
  const diagrams = document.querySelectorAll('.mermaid')
  console.log('找到图表数量:', diagrams.length)
  
  for (const diagram of diagrams) {
    if (renderToken !== engineState.renderToken) return
    if (diagram.querySelector('svg')) continue

    try {
      const diagramSource = (diagram.textContent || '').trim()
      if (!isLikelyMermaidSource(diagramSource)) {
        console.warn('跳过非 Mermaid 源文本容器')
        continue
      }

      console.log('渲染图表内容:', diagramSource.substring(0, 100) + '...')
      const groupInfo = buildColorGroupsFromSource(diagramSource)
      // 为每个图表生成唯一ID
      const id = 'mermaid-' + Math.random().toString(36).substr(2, 9)
      const { svg, bindFunctions } = await mermaid.render(id, diagramSource)
      diagram.innerHTML = svg
      console.log('图表渲染成功')
      
      // 为节点添加深度类名
      setTimeout(() => addDepthClasses(diagram, groupInfo), 100)
    } catch (error) {
      console.error('Mermaid 渲染失败:', error)
      diagram.innerHTML = `<div class="error">流程图渲染失败: ${error.message}</div>`
    }
  }
}

function isLikelyMermaidSource(source) {
  if (!source) return false
  if (source.startsWith('#mermaid-')) return false

  const normalized = source
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('%%'))
    .join('\n')

  return /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|requirementDiagram|C4Context|C4Container|C4Component|block-beta|architecture-beta|sankey-beta|xychart-beta)\b/.test(normalized)
}

function extractNodeLabel(raw) {
  if (!raw) return ''
  const cleaned = raw.replace(/^[\[\(\{]/, '').replace(/[\]\)\}]$/, '')
  return cleaned.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
}

function splitByArrow(segment) {
  const arrows = ['-->', '-.->', '==>', '--o', '--x', '---']
  let idx = -1
  let token = null
  for (const arrow of arrows) {
    const found = segment.indexOf(arrow)
    if (found !== -1 && (idx === -1 || found < idx)) {
      idx = found
      token = arrow
    }
  }
  if (idx === -1) return null
  return {
    left: segment.slice(0, idx).trim(),
    right: segment.slice(idx + token.length).trim()
  }
}

function extractIdFromSegment(segment) {
  let value = (segment || '').trim()
  if (value.startsWith('|')) {
    const end = value.indexOf('|', 1)
    if (end !== -1) {
      value = value.slice(end + 1).trim()
    }
  }
  const match = value.match(/^([A-Za-z0-9_]+)/)
  return match ? match[1] : ''
}

function parseNodeInSegment(segment, nodes) {
  const idMatch = segment.match(/^([A-Za-z0-9_]+)/)
  if (!idMatch) return
  const id = idMatch[1]
  const labelMatch = segment.match(/^[A-Za-z0-9_]+\s*[\[\(\{]([^\]\)\}]*)/)
  if (labelMatch && labelMatch[1]) {
    const label = extractNodeLabel(labelMatch[1])
    if (label) {
      nodes.set(id, label)
    }
  }
}

function parseMermaidGraph(source) {
  const nodes = new Map()
  const edges = []
  const allNodeIds = new Set()
  const lines = source.split('\n')

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('%%')) continue
    const segments = trimmed.split(';').map(item => item.trim()).filter(Boolean)

    for (const segment of segments) {
      let remaining = segment
      let foundEdge = false

      while (true) {
        const split = splitByArrow(remaining)
        if (!split) break
        foundEdge = true

        const from = extractIdFromSegment(split.left)
        const to = extractIdFromSegment(split.right)
        if (from && to) {
          edges.push({ from, to })
          allNodeIds.add(from)
          allNodeIds.add(to)
        }

        parseNodeInSegment(split.left, nodes)
        parseNodeInSegment(split.right, nodes)

        remaining = split.right
      }

      if (!foundEdge) {
        parseNodeInSegment(remaining, nodes)
      }
    }
  }

  nodes.forEach((_, id) => allNodeIds.add(id))

  return { nodes, edges, allNodeIds }
}

function buildColorGroupsFromSource(source) {
  const { nodes, edges, allNodeIds } = parseMermaidGraph(source)
  const targetToSources = new Map()
  const sourceToTargets = new Map()

  edges.forEach(({ from, to }) => {
    if (!targetToSources.has(to)) targetToSources.set(to, new Set())
    targetToSources.get(to).add(from)

    if (!sourceToTargets.has(from)) sourceToTargets.set(from, new Set())
    sourceToTargets.get(from).add(to)
  })

  class UnionFind {
    constructor(ids) {
      this.parent = new Map()
      this.rank = new Map()
      ids.forEach(id => {
        this.parent.set(id, id)
        this.rank.set(id, 0)
      })
    }
    find(id) {
      const parent = this.parent.get(id)
      if (parent === id) return id
      const root = this.find(parent)
      this.parent.set(id, root)
      return root
    }
    union(a, b) {
      const rootA = this.find(a)
      const rootB = this.find(b)
      if (rootA === rootB) return
      const rankA = this.rank.get(rootA)
      const rankB = this.rank.get(rootB)
      if (rankA < rankB) {
        this.parent.set(rootA, rootB)
      } else if (rankA > rankB) {
        this.parent.set(rootB, rootA)
      } else {
        this.parent.set(rootB, rootA)
        this.rank.set(rootA, rankA + 1)
      }
    }
  }

  const uf = new UnionFind(allNodeIds)
  const unionAll = (members) => {
    if (!members || members.size < 2) return
    const ids = Array.from(members)
    for (let i = 1; i < ids.length; i++) {
      uf.union(ids[0], ids[i])
    }
  }

  targetToSources.forEach(unionAll)
  sourceToTargets.forEach(unionAll)

  const compMembers = new Map()
  allNodeIds.forEach(id => {
    const root = uf.find(id)
    if (!compMembers.has(root)) compMembers.set(root, new Set())
    compMembers.get(root).add(id)
  })

  const compParents = new Map()
  const compChildren = new Map()
  edges.forEach(({ from, to }) => {
    const parent = uf.find(from)
    const child = uf.find(to)
    if (parent === child) return
    if (!compParents.has(child)) compParents.set(child, new Set())
    compParents.get(child).add(parent)
    if (!compChildren.has(parent)) compChildren.set(parent, new Set())
    compChildren.get(parent).add(child)
  })

  const compIds = Array.from(compMembers.keys())
  const indegree = new Map(compIds.map(id => [id, compParents.get(id)?.size || 0]))
  const queue = compIds.filter(id => (indegree.get(id) || 0) === 0)
  const order = []

  while (queue.length) {
    const current = queue.shift()
    order.push(current)
    const children = compChildren.get(current)
    if (!children) continue
    children.forEach(child => {
      indegree.set(child, (indegree.get(child) || 0) - 1)
      if (indegree.get(child) === 0) {
        queue.push(child)
      }
    })
  }

  compIds.forEach(id => {
    if (!order.includes(id)) order.push(id)
  })

  const compGroup = new Map()
  let groupIndex = 0

  const pickGroup = (forbidden) => {
    for (let i = 0; i < COLOR_GROUP_COUNT; i++) {
      const candidate = (groupIndex + i) % COLOR_GROUP_COUNT
      if (!forbidden.has(candidate)) {
        return candidate
      }
    }
    return groupIndex % COLOR_GROUP_COUNT
  }

  order.forEach(comp => {
    const forbidden = new Set()
    const parents = compParents.get(comp)
    if (parents) {
      parents.forEach(parent => {
        if (compGroup.has(parent)) forbidden.add(compGroup.get(parent))
      })
    }
    const group = pickGroup(forbidden)
    compGroup.set(comp, group)
    groupIndex = (group + 1) % COLOR_GROUP_COUNT
  })

  let changed = true
  let guard = 0
  while (changed && guard < compIds.length * 2) {
    changed = false
    guard += 1
    edges.forEach(({ from, to }) => {
      const parent = uf.find(from)
      const child = uf.find(to)
      if (parent === child) return
      const parentGroup = compGroup.get(parent)
      const childGroup = compGroup.get(child)
      if (parentGroup === childGroup) {
        const forbidden = new Set()
        const parents = compParents.get(child)
        if (parents) {
          parents.forEach(p => forbidden.add(compGroup.get(p)))
        }
        let next = (childGroup + 1) % COLOR_GROUP_COUNT
        for (let i = 0; i < COLOR_GROUP_COUNT; i++) {
          if (!forbidden.has(next)) break
          next = (next + 1) % COLOR_GROUP_COUNT
        }
        if (next !== childGroup) {
          compGroup.set(child, next)
          changed = true
        }
      }
    })
  }

  const idToGroup = new Map()
  compMembers.forEach((members, comp) => {
    const group = compGroup.get(comp)
    members.forEach(id => idToGroup.set(id, group))
  })

  const labelToGroup = new Map()
  nodes.forEach((label, id) => {
    const group = idToGroup.get(id)
    if (label && group !== undefined) {
      labelToGroup.set(label, group)
    }
  })

  return { idToGroup, labelToGroup }
}

function normalizeNodeId(id) {
  if (!id) return ''
  const prefixes = ['flowchart', 'graph', 'node']
  let result = id
  const parts = result.split('-')
  if (parts.length > 1 && prefixes.includes(parts[0])) {
    result = parts.slice(1).join('-')
  }
  if (result.includes('-')) {
    result = result.replace(/-\d+$/, '')
  }
  return result
}

function getNodeId(node) {
  const dataId = node.getAttribute('data-id')
  if (dataId) return dataId
  const idAttr = node.getAttribute('id')
  if (idAttr) return normalizeNodeId(idAttr)
  const title = node.querySelector('title')
  if (title && title.textContent) return normalizeNodeId(title.textContent.trim())
  return ''
}

const COLOR_GROUP_COUNT = 5
const labelColorMap = new Map()
let nextColorGroupIndex = 0

function normalizeLabel(text) {
  return (text || '').replace(/\s+/g, ' ').trim()
}

function getNodeLabel(node) {
  const svgText = node.querySelector('text')
  if (svgText && svgText.textContent) {
    return normalizeLabel(svgText.textContent)
  }

  const htmlLabel = node.querySelector('.nodeLabel, .label, foreignObject')
  if (htmlLabel && htmlLabel.textContent) {
    return normalizeLabel(htmlLabel.textContent)
  }

  return ''
}

function resolveColorGroup(label) {
  if (!label) {
    return 0
  }

  if (label.includes('需求') || label.includes('技术') || 
      label.includes('原型') || label.includes('功能') ||
      label.includes('测试') || label.includes('部署') ||
      label.includes('运维')) {
    return 0
  }

  if (label.includes('用户') || label.includes('竞品') ||
      label.includes('评估') || label.includes('核心') ||
      label.includes('验证') || label.includes('上线') ||
      label.includes('监控')) {
    return 1
  }

  if (label.includes('分析') || label.includes('选型') ||
      label.includes('可行性') || label.includes('辅助') ||
      label.includes('产品')) {
    return 2
  }

  if (!labelColorMap.has(label)) {
    labelColorMap.set(label, nextColorGroupIndex)
    nextColorGroupIndex = (nextColorGroupIndex + 1) % COLOR_GROUP_COUNT
  }

  return labelColorMap.get(label)
}

// 为mermaid节点添加颜色类名
function addDepthClasses(container, groupInfo = {}) {
  console.log('开始为节点添加颜色类名')
  const nodes = container.querySelectorAll('.node')
  console.log('找到节点数量:', nodes.length)
  
  if (nodes.length === 0) {
    console.log('未找到任何节点，可能需要等待渲染完成')
    return
  }
  
  nodes.forEach((node, index) => {
    const nodeId = getNodeId(node)
    const label = getNodeLabel(node)
    if (!label) {
      console.log('节点', index, '未找到文本内容')
      return
    }

    console.log('处理节点:', label)
    let colorGroup = null
    if (nodeId && groupInfo.idToGroup && groupInfo.idToGroup.has(nodeId)) {
      colorGroup = groupInfo.idToGroup.get(nodeId)
    } else if (groupInfo.labelToGroup && groupInfo.labelToGroup.has(label)) {
      colorGroup = groupInfo.labelToGroup.get(label)
    }

    if (colorGroup === null || colorGroup === undefined) {
      colorGroup = resolveColorGroup(label)
    }
    console.log('节点', label, '分配到颜色组:', colorGroup)
    
    const colorClass = `color-group-${colorGroup}`
    node.classList.add(colorClass)
    
    const shapeElements = node.querySelectorAll('rect, circle, ellipse, polygon')
    shapeElements.forEach(shape => {
      shape.classList.add(colorClass)
    })
    
    console.log('节点', label, '已添加类名:', colorClass)
  })
  
  console.log('颜色类名添加完成')
}

// 构建文档列表
function buildMarkdownDocs(modules) {
  const entries = Object.entries(modules)
    .map(([path, content]) => ({
      path,
      label: getDocLabel(path),
      content: typeof content === 'string'
        ? content
        : typeof content?.default === 'string'
          ? content.default
          : ''
    }))
    .filter(item => item.content)

  entries.sort((a, b) => a.label.localeCompare(b.label, 'zh-Hans-CN', { numeric: true }))
  return entries
}

function normalizeDocs(docs) {
  if (!Array.isArray(docs)) return []
  return docs
    .map((doc, index) => {
      if (!doc || typeof doc.content !== 'string') return null
      const path = String(doc.path || doc.id || `doc-${index + 1}`)
      const label = String(doc.label || getDocLabel(path))
      return { path, label, content: doc.content }
    })
    .filter(Boolean)
}

function selectDefaultDoc(docs, defaultDocId) {
  if (!docs.length) return null
  if (defaultDocId) {
    const byId = docs.find(doc => doc.path === defaultDocId)
    if (byId) return byId
  }
  return docs.find(doc => doc.path.includes('影像处理总结.md')) || docs.find(doc => doc.path.includes('projecthandover.md')) || docs[0]
}

// 从路径生成显示名称
function getDocLabel(path) {
  const fileName = path.split('/').pop() || path
  return fileName.replace(/\.md$/i, '')
}

// 从 Markdown 提取标题并生成目录
function generateTOC(markdown) {
  const cleanMarkdown = markdown.replace(/<!--[\s\S]*?-->/g, '')
  const lines = cleanMarkdown.replace(/\r\n/g, '\n').split('\n')
  const headings = []
  let headingId = 1
  
  for (const line of lines) {
    const match = line.match(/^(#{1,6})\s+(.+)$/)
    if (match) {
      const level = match[1].length
      const text = escapeMarkup(match[2].trim())
      if (text) {
        headings.push({ level, text, id: `heading-${headingId++}` })
      }
    }
  }
  
  const tocStructure = buildTOCStructure(headings)
  return generateTOCHTML(tocStructure)
}

// 按层级构建目录树
function buildTOCStructure(headings) {
  if (headings.length === 0) return []
  
  const root = { children: [], level: 0 }
  const stack = [root]
  
  for (const heading of headings) {
    while (stack.length > 1 && stack[stack.length - 1].level >= heading.level) {
      stack.pop()
    }
    
    const newItem = { ...heading, children: [] }
    stack[stack.length - 1].children.push(newItem)
    stack.push(newItem)
  }
  
  return root.children
}

// 生成目录 HTML
function generateTOCHTML(items, level = 0) {
  if (!items || items.length === 0) return ''
  
  let html = '<ul>'
  
  for (const item of items) {
    const hasChildren = item.children && item.children.length > 0
    const toggleClass = hasChildren ? 'toggle' : 'toggle no-children'
    const toggleBtn = `<span class="${toggleClass}"></span>`
    
    html += `<li>
      <div class="toc-item">
        ${toggleBtn}
        <a href="#${item.id}">${item.text}</a>
      </div>
      ${hasChildren ? generateTOCHTML(item.children, level + 1) : ''}
    </li>`
  }
  
  html += '</ul>'
  return html
}

// 为标题添加 id 并初始化目录交互
function addHeadingIds() {
  const headings = document.querySelectorAll('#content h1, #content h2, #content h3, #content h4, #content h5, #content h6')
  let headingId = 1
  
  headings.forEach(heading => {
    const id = `heading-${headingId++}`
    heading.id = id
  })
  
  initTOCToggle()
  
  initScrollListener()
  
  initTOCClick()
}

// 监听滚动并更新目录高亮
function initScrollListener() {
  const content = document.getElementById('content')
  
  updateActiveTOC()
  
  content.addEventListener('scroll', updateActiveTOC)
  
  window.addEventListener('resize', updateActiveTOC)
}

// 更新当前目录高亮
function updateActiveTOC() {
  const content = document.getElementById('content');
  if (!content) return;
  
  const OFFSET = 100; 
  const scrollPosition = content.scrollTop + OFFSET;
  
  const headings = Array.from(document.querySelectorAll('#content h1, #content h2, #content h3, #content h4, #content h5, #content h6'));
  
  let activeHeading = null;
  for (let i = 0; i < headings.length; i++) {
    if (headings[i].offsetTop <= scrollPosition) {
      activeHeading = headings[i];
    } else {
      break;
    }
  }
  
  if (activeHeading) {
    updateTOCActiveLink(activeHeading.id);
    expandTOCItem(activeHeading.id);
  } else {
    document.querySelectorAll('#toc a.active').forEach(el => el.classList.remove('active'));
  }
}

// 判断元素是否在可视范围内
function isElementVisible(element) {
  if (!element) return false
  
  const content = document.getElementById('content')
  
  const scrollTop = content.scrollTop
  const clientHeight = content.clientHeight
  const scrollBottom = scrollTop + clientHeight
  
  const elementRect = element.getBoundingClientRect()
  const contentRect = content.getBoundingClientRect()
  
  const elementTop = elementRect.top - contentRect.top
  const elementBottom = elementTop + elementRect.height
  
  return (
    elementBottom > scrollTop &&
    elementTop < scrollBottom
  )
}

// 更新目录链接高亮
function updateTOCActiveLink(activeId) {
  const tocLinks = document.querySelectorAll('#toc a')
  tocLinks.forEach(link => {
    link.classList.remove('active')
  })
  
  const activeLink = document.querySelector(`#toc a[href="#${activeId}"]`)
  if (activeLink) {
    activeLink.classList.add('active')
    
    scrollSidebarToActiveItem(activeLink)
  }
}

// 保证目录高亮项在侧边栏可见
function scrollSidebarToActiveItem(activeLink) {
  const sidebar = document.getElementById('sidebar')
  if (!sidebar || !activeLink) return
  
  const sidebarRect = sidebar.getBoundingClientRect()
  const linkRect = activeLink.getBoundingClientRect()
  
  if (linkRect.top < sidebarRect.top || linkRect.bottom > sidebarRect.bottom) {
    activeLink.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest'
      })
  }
}

// 目录折叠与展开
function initTOCToggle() {
  const toggleButtons = document.querySelectorAll('#toc .toggle:not(.no-children)')
  
  toggleButtons.forEach(toggle => {
    const tocItem = toggle.closest('.toc-item')
    const listItem = tocItem.closest('li')
    const sublist = listItem.querySelector('ul')
    
    if (sublist) {
      toggle.addEventListener('click', () => {
        toggle.classList.toggle('collapsed')
        sublist.classList.toggle('collapsed')
      })
    }
  })
}

// 展开当前目录及父级目录
function expandTOCItem(activeId) {
  const activeLink = document.querySelector(`#toc a[href="#${activeId}"]`)
  if (!activeLink) return
  
  let currentLi = activeLink.closest('li')
  
  while (currentLi) {
    const parentUl = currentLi.parentElement
    
    if (parentUl && parentUl.id === 'toc') {
      break
    }
    
    if (parentUl && parentUl.classList.contains('collapsed')) {
      parentUl.classList.remove('collapsed')
    }
    
    const parentLi = parentUl.closest('li')
    if (parentLi) {
      const toggle = parentLi.querySelector('.toggle')
      if (toggle && toggle.classList.contains('collapsed')) {
        toggle.classList.remove('collapsed')
      }
    }
    
    currentLi = parentLi
  }
}

// 目录点击跳转
function initTOCClick() {
  const tocLinks = document.querySelectorAll('#toc a')
  
  tocLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault()
      const targetId = link.getAttribute('href').substring(1)
      const targetElement = document.getElementById(targetId)
      
      if (targetElement) {
        const content = document.getElementById('content')
        const targetPosition = targetElement.offsetTop - 20
        content.scrollTo({
          top: targetPosition,
          behavior: 'smooth'
        })
        
        setTimeout(() => {
          updateTOCActiveLink(targetId)
          expandTOCItem(targetId)
        }, 100)
      }
    })
  })
}

// 绑定导出按钮
function initExportActions() {
  const pdfBtn = document.querySelector('[data-export="pdf"]')
  const wordBtn = document.querySelector('[data-export="word"]')

  if (pdfBtn) {
    pdfBtn.addEventListener('click', () => exportToPDF())
  }
  if (wordBtn) {
    wordBtn.addEventListener('click', () => exportToWord())
  }
}

// 绑定文档选择器
function initDocSelector() {
  const select = document.getElementById('doc-select')
  if (!select) return

  select.addEventListener('change', (event) => {
    const { markdownDocs, currentDoc } = engineState
    const nextPath = event.target.value
    const nextDoc = markdownDocs.find(doc => doc.path === nextPath)
    if (!nextDoc || nextDoc.path === currentDoc?.path) return
    engineState.currentDoc = nextDoc
    renderMarkdown()
  })
}

function initCodeCopyButtons() {
  const codeBlocks = document.querySelectorAll('#content pre > code')
  codeBlocks.forEach((code) => {
    const pre = code.closest('pre')
    if (!pre || pre.querySelector('.code-copy-btn')) return

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'code-copy-btn'
    button.textContent = '复制'

    button.addEventListener('click', async () => {
      const text = code.textContent || ''
      const copied = await copyToClipboard(text)
      button.textContent = copied ? '已复制' : '复制失败'
      setTimeout(() => {
        button.textContent = '复制'
      }, 1200)
    })

    pre.appendChild(button)
  })
}

async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (error) {
    console.warn('Clipboard API 复制失败，尝试降级方案', error)
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const success = document.execCommand('copy')
    document.body.removeChild(textarea)
    return success
  } catch (error) {
    console.error('降级复制失败', error)
    return false
  }
}

function toContentInterval(rect, contentRect, scrollTop, padding = 0) {
  return {
    top: rect.top - contentRect.top + scrollTop - padding,
    bottom: rect.bottom - contentRect.top + scrollTop + padding
  }
}

function mergeIntervals(intervals) {
  const sorted = intervals
    .filter(interval => interval.bottom - interval.top > 0.5)
    .sort((a, b) => a.top - b.top || a.bottom - b.bottom)
  const merged = []

  for (const interval of sorted) {
    const previous = merged[merged.length - 1]
    // 只合并真正重叠的区间。相邻表格行的边界通常完全相等，若也合并，
    // 整张长表会重新变成一个不可分页的大块。
    if (previous && interval.top < previous.bottom - 0.5) {
      previous.bottom = Math.max(previous.bottom, interval.bottom)
    } else {
      merged.push({ ...interval })
    }
  }

  return merged
}

// Range.getClientRects() 会返回文本换行后的每一行矩形。分页时把这些矩形视为
// “禁止切割区”，比仅测量 p/li/ul 的整体高度更准确，也不会被嵌套列表误导。
function getTextLineDetails(content, contentRect) {
  const lines = []
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT)
  let textNode = walker.nextNode()

  while (textNode) {
    const parent = textNode.parentElement
    const ignored = parent?.closest(
      'script, style, .code-copy-btn, .mermaid-zoom-controls, [aria-hidden="true"]'
    )
    if (!ignored && textNode.textContent?.trim()) {
      const range = document.createRange()
      range.selectNodeContents(textNode)
      for (const rect of range.getClientRects()) {
        if (rect.width > 0.5 && rect.height > 0.5) {
          // 粗体、中文字体抗锯齿和 text-shadow 的实际 canvas 像素可能超出
          // Range 矩形；上下各留 6px，兼顾坐标取整和字形外溢。
          lines.push({
            ...toContentInterval(rect, contentRect, content.scrollTop, 6),
            rawTop: rect.top - contentRect.top + content.scrollTop,
            rawBottom: rect.bottom - contentRect.top + content.scrollTop,
            textNode
          })
        }
      }
      range.detach?.()
    }
    textNode = walker.nextNode()
  }

  return lines.sort((a, b) => a.top - b.top || a.bottom - b.bottom)
}

function getKeepTogetherBlocks(content, contentRect) {
  const nodes = content.querySelectorAll(
    'h1, h2, h3, h4, h5, h6, p, li, tr, pre, blockquote, img, .mermaid, .mermaid-zoom-wrapper'
  )

  return Array.from(nodes)
    .filter(node => {
      // 含子列表的 li 高度会包含整个嵌套列表，不能作为一个整体避让，否则会
      // 在下一页再次命中同一个大块并触发硬切。
      if (node.matches('li') && node.querySelector(':scope > ul, :scope > ol')) return false
      // Mermaid wrapper 与内部 .mermaid 只保留外层，避免重复区间。
      if (node.matches('.mermaid') && node.closest('.mermaid-zoom-wrapper')) return false
      return true
    })
    .map(node => ({
      ...toContentInterval(node.getBoundingClientRect(), contentRect, content.scrollTop),
      node
    }))
    .filter(interval => interval.bottom - interval.top > 4)
}

function getPaginationLayout(content) {
  const contentRect = content.getBoundingClientRect()
  const textLineDetails = getTextLineDetails(content, contentRect)
  return {
    textLines: mergeIntervals(textLineDetails),
    textLineDetails,
    keepTogetherBlocks: getKeepTogetherBlocks(content, contentRect)
  }
}

function assertBreaksDoNotCrossText(breaks, textLines) {
  const invalidBreak = breaks.slice(1, -1).find(pageBreak => (
    textLines.some(line => line.top < pageBreak && line.bottom > pageBreak)
  ))
  if (invalidBreak !== undefined) {
    throw new Error(`PDF 分页仍穿过文字行（位置 ${invalidBreak.toFixed(1)}px）`)
  }
}

function removePdfPageSpacers(content) {
  content.querySelectorAll('[data-pdf-page-spacer]').forEach(spacer => {
    const parent = spacer.parentNode
    spacer.remove()
    parent?.normalize()
  })
}

function wrapPdfBracketLabels(content) {
  const bracketPattern = /【[^【】\r\n]*】/g
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT)
  const textNodes = []
  let textNode = walker.nextNode()

  while (textNode) {
    const excluded = textNode.parentElement?.closest(
      'pre, code, script, style, svg, canvas, .mermaid, [data-pdf-bracket-label]'
    )
    if (!excluded && bracketPattern.test(textNode.textContent || '')) textNodes.push(textNode)
    bracketPattern.lastIndex = 0
    textNode = walker.nextNode()
  }

  textNodes.forEach(node => {
    const text = node.textContent || ''
    const fragment = document.createDocumentFragment()
    let lastIndex = 0
    bracketPattern.lastIndex = 0

    for (const match of text.matchAll(bracketPattern)) {
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)))
      }

      const label = document.createElement('span')
      label.dataset.pdfBracketLabel = 'true'
      label.setAttribute('aria-label', match[0])
      Object.assign(label.style, {
        display: 'inline-flex',
        flexWrap: 'nowrap',
        whiteSpace: 'nowrap',
        alignItems: 'baseline',
        verticalAlign: 'baseline',
        letterSpacing: '0',
        wordSpacing: '0',
        fontKerning: 'none',
        fontVariantLigatures: 'none',
        fontFamily: "'Microsoft YaHei', 'Noto Sans SC', 'PingFang SC', sans-serif"
      })

      for (const character of match[0]) {
        const glyph = document.createElement('span')
        glyph.textContent = character
        glyph.setAttribute('aria-hidden', 'true')
        Object.assign(glyph.style, {
          display: 'inline-block',
          flex: '0 0 auto',
          width: 'auto',
          minWidth: '0',
          letterSpacing: '0'
        })
        label.appendChild(glyph)
      }

      fragment.appendChild(label)
      lastIndex = match.index + match[0].length
    }

    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)))
    }
    node.replaceWith(fragment)
  })
}

function unwrapPdfBracketLabels(content) {
  content.querySelectorAll('[data-pdf-bracket-label]').forEach(label => {
    const parent = label.parentNode
    label.replaceWith(document.createTextNode(label.getAttribute('aria-label') || label.textContent || ''))
    parent?.normalize()
  })
}

function getHeadingIntervals(layout, padding = 8) {
  return layout.keepTogetherBlocks
    .filter(block => block.node?.matches('h1, h2, h3, h4, h5, h6'))
    .map(block => ({ top: block.top - padding, bottom: block.bottom + padding }))
}

function findFirstUnsafeBoundary(contentHeight, usableHeight, protectedIntervals) {
  for (let boundary = usableHeight; boundary < contentHeight - 1; boundary += usableHeight) {
    if (protectedIntervals.some(interval => (
      interval.top < boundary && interval.bottom > boundary
    ))) {
      return boundary
    }
  }
  return null
}

function getBlockDepth(node, content) {
  let depth = 0
  let current = node
  while (current && current !== content) {
    depth += 1
    current = current.parentElement
  }
  return depth
}

function findMovableBlock(content, boundary, usableHeight) {
  const contentRect = content.getBoundingClientRect()
  const candidates = Array.from(content.querySelectorAll(
    'h1, h2, h3, h4, h5, h6, p, li, tr, pre, blockquote, table'
  )).map(node => {
    const interval = toContentInterval(node.getBoundingClientRect(), contentRect, content.scrollTop)
    const isWholeListItem = node.matches('li') && !node.querySelector(':scope > ul, :scope > ol')
    const movePriority = isWholeListItem || node.matches('tr') ? 0 : 1
    return { ...interval, node, depth: getBlockDepth(node, content), movePriority }
  }).filter(item => (
    item.top < boundary &&
    item.bottom > boundary &&
    item.bottom - item.top <= usableHeight - 12 &&
    item.top > boundary - usableHeight + 1
  ))

  return candidates.sort((a, b) => (
    a.movePriority - b.movePriority ||
    b.depth - a.depth ||
    (a.bottom - a.top) - (b.bottom - b.top) ||
    b.top - a.top
  ))[0] || null
}

function createPageSpacer(height, tagName = 'div') {
  const spacer = document.createElement(tagName)
  spacer.dataset.pdfPageSpacer = 'true'
  spacer.setAttribute('aria-hidden', 'true')
  Object.assign(spacer.style, {
    display: 'block',
    width: '100%',
    height: `${Math.max(1, height)}px`,
    minHeight: `${Math.max(1, height)}px`,
    margin: '0',
    padding: '0',
    border: '0',
    background: 'transparent',
    boxSizing: 'border-box',
    listStyle: 'none'
  })
  return spacer
}

function insertSpacerBeforeBlock(block, height) {
  if (block.matches('tr')) {
    const spacerRow = document.createElement('tr')
    spacerRow.dataset.pdfPageSpacer = 'true'
    spacerRow.setAttribute('aria-hidden', 'true')
    const cell = document.createElement('td')
    cell.colSpan = Math.max(1, block.children.length)
    Object.assign(cell.style, {
      height: `${Math.max(1, height)}px`,
      minHeight: `${Math.max(1, height)}px`,
      padding: '0',
      border: '0',
      background: 'transparent'
    })
    spacerRow.appendChild(cell)
    block.parentNode.insertBefore(spacerRow, block)
    return
  }

  block.parentNode.insertBefore(createPageSpacer(height), block)
}

function getCharacterTop(textNode, offset, content, contentRect) {
  const range = document.createRange()
  range.setStart(textNode, offset)
  range.setEnd(textNode, Math.min(offset + 1, textNode.length))
  const rect = range.getBoundingClientRect()
  range.detach?.()
  return rect.top - contentRect.top + content.scrollTop
}

function findLineStartOffset(line, content) {
  const { textNode, rawTop } = line
  if (!textNode?.isConnected || textNode.length < 2) return 0
  const contentRect = content.getBoundingClientRect()
  let low = 0
  let high = textNode.length - 1

  while (low < high) {
    const middle = Math.floor((low + high) / 2)
    if (getCharacterTop(textNode, middle, content, contentRect) < rawTop - 0.5) {
      low = middle + 1
    } else {
      high = middle
    }
  }
  return low
}

function insertInlineLineSpacer(content, boundary, line) {
  const offset = findLineStartOffset(line, content)
  if (!line.textNode?.isConnected) return false
  if (offset <= 0) {
    const spacer = createPageSpacer(boundary - line.rawTop + 4, 'span')
    line.textNode.parentNode.insertBefore(spacer, line.textNode)
    return true
  }
  if (offset >= line.textNode.length) return false
  const tail = line.textNode.splitText(offset)
  const spacer = createPageSpacer(boundary - line.rawTop + 4, 'span')
  tail.parentNode.insertBefore(spacer, tail)
  return true
}

// html2canvas 截图前先真实改变 DOM 流。每次只处理最前面的危险页边界，
// 插入占位后重新测量，直到所有固定页边界都处在空白区域。
function reflowContentForPdf(content, usableHeight) {
  removePdfPageSpacers(content)
  const maxPasses = 500

  for (let pass = 0; pass < maxPasses; pass++) {
    const layout = getPaginationLayout(content)
    const contentHeight = content.scrollHeight
    // DOM 重排只判断真实行框；额外安全边距仅供最终 canvas 切片使用，
    // 否则边界落在保护区而非文字本身时会出现“找不到可移动元素”。
    const rawTextLines = mergeIntervals(layout.textLineDetails.map(line => ({
      top: line.rawTop,
      bottom: line.rawBottom
    })))
    const protectedIntervals = mergeIntervals([
      ...rawTextLines,
      ...getHeadingIntervals(layout, 0)
    ])
    const boundary = findFirstUnsafeBoundary(contentHeight, usableHeight, protectedIntervals)
    if (boundary === null) return layout

    const block = findMovableBlock(content, boundary, usableHeight)
    if (block) {
      insertSpacerBeforeBlock(block.node, boundary - block.top + 4)
      continue
    }

    const crossingLine = layout.textLineDetails.find(line => (
      line.rawTop < boundary && line.rawBottom > boundary
    ))
    if (crossingLine && insertInlineLineSpacer(content, boundary, crossingLine)) continue

    throw new Error(`无法在第 ${Math.ceil(boundary / usableHeight)} 页前重排文字`)
  }

  throw new Error('PDF 分页重排次数过多，请检查超长不可拆分元素')
}

function moveBreakBeforeProtectedContent(candidate, pageStart, protectedIntervals) {
  // 从理想页尾向上移动到最近的行间空白。文字区间已经向上下各扩展 2px，
  // 因此 canvas 坐标取整后也不会擦到字形边缘。
  for (let i = protectedIntervals.length - 1; i >= 0; i--) {
    const interval = protectedIntervals[i]
    if (interval.bottom <= pageStart || interval.top >= candidate) continue
    if (interval.top < candidate && interval.bottom > candidate) candidate = interval.top
  }
  return candidate
}

function buildSafePageBreaks(contentHeight, usableHeight, layout) {
  const breaks = [0]
  const protectedIntervals = mergeIntervals([
    ...layout.textLines,
    ...getHeadingIntervals(layout)
  ])
  let pageStart = 0

  while (pageStart < contentHeight - 1) {
    const idealEnd = Math.min(contentHeight, pageStart + usableHeight)
    if (idealEnd >= contentHeight) {
      breaks.push(contentHeight)
      break
    }

    const pageEnd = moveBreakBeforeProtectedContent(idealEnd, pageStart, protectedIntervals)
    if (pageEnd <= pageStart + 1) {
      throw new Error('无法找到不截断文字的 PDF 分页位置')
    }
    breaks.push(pageEnd)
    pageStart = pageEnd
  }

  assertBreaksDoNotCrossText(breaks, protectedIntervals)
  return breaks
}

function getSafeCanvasRows(imageData, width, height) {
  const { data } = imageData
  const safeRows = new Array(height).fill(true)
  const xStart = Math.floor(width * 0.025)
  const xEnd = Math.ceil(width * 0.975)
  const step = 2
  const samples = Math.max(1, Math.ceil((xEnd - xStart) / step))
  const inkLimit = Math.max(8, Math.floor(samples * 0.008))

  for (let y = 0; y < height; y++) {
    let darkPixels = 0
    let colorEdges = 0
    let previousR = -1
    let previousG = -1
    let previousB = -1

    for (let x = xStart; x < xEnd; x += step) {
      const index = (y * width + x) * 4
      const r = data[index]
      const g = data[index + 1]
      const b = data[index + 2]
      const alpha = data[index + 3]
      if (alpha > 16) {
        const luminance = r * 0.2126 + g * 0.7152 + b * 0.0722
        if (luminance < 170) darkPixels += 1
        if (
          previousR >= 0 &&
          Math.abs(r - previousR) + Math.abs(g - previousG) + Math.abs(b - previousB) > 72
        ) {
          colorEdges += 1
        }
      }
      previousR = r
      previousG = g
      previousB = b
    }

    safeRows[y] = darkPixels <= inkLimit && colorEdges <= inkLimit
  }

  return safeRows
}

function findCanvasSafeBreak(canvas, pageStart, idealEnd, ratio) {
  const context = canvas.getContext('2d', { willReadFrequently: true })
  const safeBandHeight = Math.max(8, Math.ceil(5 * ratio))
  const minPageContent = Math.max(safeBandHeight, Math.ceil(80 * ratio))
  const earliestBreak = Math.min(idealEnd - 1, pageStart + minPageContent)
  const chunkHeight = 520
  let chunkEnd = idealEnd

  while (chunkEnd > earliestBreak) {
    const chunkStart = Math.max(earliestBreak, chunkEnd - chunkHeight)
    const height = chunkEnd - chunkStart
    const imageData = context.getImageData(0, chunkStart, canvas.width, height)
    const safeRows = getSafeCanvasRows(imageData, canvas.width, height)

    for (let localY = height - safeBandHeight; localY >= 0; localY--) {
      let bandIsSafe = true
      for (let bandY = 0; bandY < safeBandHeight; bandY++) {
        if (!safeRows[localY + bandY]) {
          bandIsSafe = false
          break
        }
      }
      if (bandIsSafe) {
        return chunkStart + localY + Math.floor(safeBandHeight / 2)
      }
    }

    // 保留一个安全带高度的重叠区域，避免空白带恰好跨越两个扫描块。
    chunkEnd = chunkStart + safeBandHeight - 1
  }

  return null
}

// 最终断点直接依据 html2canvas 的真实像素计算，不再假设 DOM 行框与截图
// 坐标完全一致。只有检测到连续的无文字水平空白带时才允许切页。
function buildCanvasPageBreaks(canvas, usablePageHeightPx, ratio) {
  const breaks = [0]
  let pageStart = 0

  while (pageStart < canvas.height - 1) {
    const idealEnd = Math.min(canvas.height, pageStart + usablePageHeightPx)
    if (idealEnd >= canvas.height) {
      breaks.push(canvas.height)
      break
    }

    const safeBreak = findCanvasSafeBreak(canvas, pageStart, idealEnd, ratio)
    if (safeBreak === null || safeBreak <= pageStart) {
      throw new Error(`第 ${breaks.length} 页找不到无文字的截图裁切位置`)
    }
    breaks.push(safeBreak)
    pageStart = safeBreak
  }

  return breaks
}

// 导出 PDF
async function exportToPDF() {
  const content = document.getElementById('content')
  if (!content) return

  const buttons = document.querySelectorAll('.export-btn')
  buttons.forEach(btn => {
    btn.disabled = true
  })

  const previous = {
    height: content.style.height,
    maxHeight: content.style.maxHeight,
    overflow: content.style.overflow,
    background: content.style.background
  }

  document.body.classList.add('is-exporting')
  content.style.height = 'auto'
  content.style.maxHeight = 'none'
  content.style.overflow = 'visible'
  content.scrollTop = 0

  try {
    console.log('[ReadMarkdownDebug] exportToPDF start: fill mermaid to canvas')
    wrapPdfBracketLabels(content)
    fillAllMermaidToCanvas(content)
    refreshAllMermaidOverlays(content)
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready
    }

    await new Promise(requestAnimationFrame)

    const rootStyles = getComputedStyle(document.documentElement)
    const exportBg =
      rootStyles.getPropertyValue('--bg-1').trim() ||
      rootStyles.getPropertyValue('--bg-0').trim() ||
      '#ffffff'

    content.style.background = exportBg

    const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
      import('html2canvas'),
      import('jspdf')
    ])

    const pdf = new jsPDF({ orientation: 'p', unit: 'px', format: 'a4', compress: true })
    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()
    const pageMargin = 35
    const captureScale = 2.6
    // html2canvas 按内容宽度等比截图，因此截图前即可换算出一页对应的 DOM 高度。
    const pageHeightDom = (content.scrollWidth * pageHeight) / pageWidth
    const usablePageHeightDom = Math.max(120, pageHeightDom - pageMargin * 2)

    reflowContentForPdf(content, usablePageHeightDom)
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

    const canvas = await html2canvas(content, {
      scale: captureScale,
      useCORS: true,
      backgroundColor: exportBg,
      windowWidth: content.scrollWidth,
      windowHeight: content.scrollHeight
    })

    const contentHeight = content.scrollHeight
    const pageHeightPx = Math.floor((canvas.width * pageHeight) / pageWidth)
    const ratio = canvas.height / contentHeight
    const pageMarginPx = Math.floor(pageMargin * ratio)
    const usablePageHeightPx = pageHeightPx - pageMarginPx * 2
    // 直接使用最终截图像素计算断点，彻底避开 DOM 与 canvas 坐标偏差。
    const breaks = buildCanvasPageBreaks(canvas, usablePageHeightPx - 1, ratio)

    const pageCanvas = document.createElement('canvas')
    const pageCtx = pageCanvas.getContext('2d')
    let pageIndex = 0

    for (let i = 0; i < breaks.length - 1; i++) {
      const offsetY = breaks[i]
      const sliceEndY = breaks[i + 1]
      const sliceHeight = sliceEndY - offsetY
      if (sliceHeight > usablePageHeightPx) {
        throw new Error(`第 ${i + 1} 页截图高度超过页面可用区域`)
      }
      pageCanvas.width = canvas.width
      pageCanvas.height = pageHeightPx

      pageCtx.clearRect(0, 0, canvas.width, pageHeightPx)
      pageCtx.fillStyle = exportBg
      pageCtx.fillRect(0, 0, canvas.width, pageHeightPx)
      
      // 在顶部留白区域绘制背景
      pageCtx.fillStyle = exportBg
      pageCtx.fillRect(0, 0, canvas.width, pageMarginPx)
      
      // 在底部留白区域绘制背景
      pageCtx.fillRect(0, pageHeightPx - pageMarginPx, canvas.width, pageMarginPx)
      
      // 绘制实际内容（从留白后开始）
      pageCtx.drawImage(
        canvas,
        0,
        offsetY,
        canvas.width,
        sliceHeight,
        0,
        pageMarginPx,
        canvas.width,
        sliceHeight
      )

      const imgData = pageCanvas.toDataURL('image/jpeg', 0.92)
      if (pageIndex > 0) {
        pdf.addPage()
      }
      pdf.addImage(imgData, 'JPEG', 0, 0, pageWidth, pageHeight)

      pageIndex += 1
    }

    pdf.save(`年终总结-${getDateStamp()}.pdf`)
  } catch (error) {
    console.error(error)
    alert(`导出 PDF 失败：${error.message}`)
  } finally {
    removePdfPageSpacers(content)
    unwrapPdfBracketLabels(content)
    content.style.height = previous.height
    content.style.maxHeight = previous.maxHeight
    content.style.overflow = previous.overflow
    content.style.background = previous.background
    document.body.classList.remove('is-exporting')

    buttons.forEach(btn => {
      btn.disabled = false
    })
  }
}

// 导出 Word
async function exportToWord() {
  const content = document.getElementById('content')
  if (!content) return

  const html = await buildWordHtmlFromContent(content)
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' })
  triggerDownload(blob, `年终总结-${getDateStamp()}.doc`)
}

async function buildWordHtmlFromContent(content) {
  const clone = content.cloneNode(true)
  const mermaidImages = await captureMermaidImages(content)
  applyMermaidImagesToClone(clone, mermaidImages)
  ensureTableCompatibility(clone)
  return buildWordHtml(clone.innerHTML)
}

function ensureTableCompatibility(container) {
  const tables = container.querySelectorAll('table')
  tables.forEach(table => {
    table.setAttribute('border', '1')
    table.setAttribute('cellpadding', '0')
    table.setAttribute('cellspacing', '0')
    table.style.borderCollapse = 'collapse'
    table.style.width = '100%'

    const cells = table.querySelectorAll('th, td')
    cells.forEach(cell => {
      cell.style.border = '1px solid #dbeafe'
      cell.style.padding = '8px 10px'
      cell.style.textAlign = 'left'
    })
  })
}

function getSvgSize(svg) {
  const widthAttr = svg.getAttribute('width')
  const heightAttr = svg.getAttribute('height')
  const width = widthAttr ? parseFloat(widthAttr) : 0
  const height = heightAttr ? parseFloat(heightAttr) : 0
  if (width && height) return { width, height }

  const viewBox = svg.getAttribute('viewBox')
  if (viewBox) {
    const parts = viewBox.split(/\s+/).map(Number)
    if (parts.length === 4 && parts[2] && parts[3]) {
      return { width: parts[2], height: parts[3] }
    }
  }

  return { width: 800, height: 450 }
}

async function captureMermaidImages(content) {
  const mermaidBlocks = Array.from(content.querySelectorAll('.mermaid'))
  if (mermaidBlocks.length === 0) return []

  fitAllMermaidToDiagram(content)
  await new Promise((resolve) => setTimeout(resolve, 80))

  const { default: html2canvas } = await import('html2canvas')
  const images = []

  for (const block of mermaidBlocks) {
    try {
      const canvas = await html2canvas(block, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff'
      })
      images.push(canvas.toDataURL('image/png'))
    } catch (error) {
      console.warn('导出 Word 时 Mermaid 转图片失败:', error)
      images.push('')
    }
  }

  return images
}

function applyMermaidImagesToClone(container, images) {
  const mermaidBlocks = Array.from(container.querySelectorAll('.mermaid'))
  mermaidBlocks.forEach((block, index) => {
    const dataUrl = images[index]
    if (!dataUrl) return
    const img = document.createElement('img')
    img.src = dataUrl
    img.style.width = '100%'
    img.style.maxWidth = '8.5cm'
    img.style.height = 'auto'
    img.style.display = 'block'
    img.style.margin = '0 auto'
    img.removeAttribute('width')
    img.removeAttribute('height')
    block.style.textAlign = 'center'
    block.innerHTML = ''
    block.appendChild(img)
  })
}

// 生成 Word HTML
function buildWordHtml(contentHtml) {
  const styles = `
    @page { size: A4; margin: 2.54cm; }
    body { font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif; color: #0f172a; line-height: 1.7; }
    h1 { font-size: 28px; font-weight: 700; margin: 0 0 18px; padding-bottom: 10px; border-bottom: 2px solid #bfdbfe; }
    h2 { font-size: 22px; font-weight: 600; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #bfdbfe; }
    h3 { font-size: 18px; font-weight: 600; margin: 20px 0 10px; }
    p { margin: 0 0 12px; }
    ul, ol { padding-left: 24px; margin: 0 0 12px; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; }
    th, td { border: 1px solid #dbeafe; padding: 8px 10px; text-align: left; }
    th { background: #eff6ff; }
    pre { background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; white-space: pre-wrap; }
    code { background: #e0f2fe; padding: 2px 4px; }
    a { color: #1d4ed8; text-decoration: none; }
    img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
    .mermaid img { width: 100%; max-width: 8.5cm; }
    .mermaid { text-align: center; }
  `

  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>年终总结</title>
    <style>${styles}</style>
  </head>
  <body>
    ${contentHtml}
  </body>
</html>`
}

// 触发下载
function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// 生成日期戳
function getDateStamp() {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${yyyy}${mm}${dd}`
}

