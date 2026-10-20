const { createMarkdownEngine } = await import('../src/index.js')
console.log('[ReadMarkdownDebug] demo running from source bundle')

const app = document.getElementById('app')
const loaderPanel = document.getElementById('loader-panel')
const dropZone = document.getElementById('drop-zone')
const fileInput = document.getElementById('file-input')
const openPickerButton = document.getElementById('open-picker')
const globalDropTip = document.getElementById('global-drop-tip')

const SERVER_DOC_PATH = `${import.meta.env.BASE_URL}mdData/API文档.md`

const state = {
  engine: null,
  dragDepth: 0
}

function normalizeLabel(fileName) {
  return fileName.replace(/\.md$/i, '')
}

function toDocPath(file, index) {
  return `local/${Date.now()}-${index}-${file.name}`
}

function isMarkdownFile(file) {
  const name = file?.name || ''
  const type = file?.type || ''
  return /\.md$/i.test(name) || type === 'text/markdown' || type === 'text/plain'
}

async function loadServerDoc() {
  const response = await fetch(SERVER_DOC_PATH)
  if (!response.ok) {
    throw new Error(`服务器文档加载失败: ${response.status}`)
  }

  return {
    path: SERVER_DOC_PATH,
    label: 'API文档',
    content: await response.text()
  }
}

async function filesToDocs(files) {
  const accepted = Array.from(files).filter(isMarkdownFile)
  if (!accepted.length) return []

  const docs = []
  for (let i = 0; i < accepted.length; i++) {
    const file = accepted[i]
    const content = await file.text()
    docs.push({
      path: toDocPath(file, i),
      label: normalizeLabel(file.name),
      content
    })
  }

  return docs
}

function showViewer() {
  loaderPanel.classList.add('hidden')
  app.classList.remove('hidden')
}

function showLoader() {
  loaderPanel.classList.remove('hidden')
  app.classList.add('hidden')
}

function setDropZoneActive(active) {
  if (active) {
    dropZone.classList.add('active')
  } else {
    dropZone.classList.remove('active')
  }
}

async function renderFromFiles(files) {
  const localDocs = await filesToDocs(files)
  console.log('[ReadMarkdownDebug] files selected', {
    totalFiles: files?.length || 0,
    markdownFiles: localDocs.length
  })
  if (!localDocs.length) {
    alert('\u672a\u8bfb\u53d6\u5230\u53ef\u7528\u7684 Markdown \u6587\u4ef6\uff08.md\uff09')
    return
  }

  const serverDoc = await loadServerDoc()
  const docs = [...localDocs, serverDoc]

  if (!state.engine) {
    state.engine = createMarkdownEngine({
      container: '#app',
      docs,
      defaultDocId: docs[0].path
    })
  } else {
    state.engine.setDocs(docs, docs[0].path)
  }

  showViewer()
  console.log('[ReadMarkdownDebug] viewer shown')
}

async function renderDefaultDoc() {
  try {
    const serverDoc = await loadServerDoc()
    state.engine = createMarkdownEngine({
      container: '#app',
      docs: [serverDoc],
      defaultDocId: SERVER_DOC_PATH
    })
    showViewer()
  } catch (error) {
    console.error('[ReadMarkdownDebug] default document load failed', error)
    alert(`默认文档加载失败：${error.message}`)
  }
}

function hasFiles(event) {
  return Array.from(event.dataTransfer?.types || []).includes('Files')
}

openPickerButton.addEventListener('click', () => {
  fileInput.click()
})

dropZone.addEventListener('click', () => {
  fileInput.click()
})

app.addEventListener('click', (event) => {
  const target = event.target.closest('[data-action="import-docs"]')
  if (!target) return
  showLoader()
  fileInput.click()
})

dropZone.addEventListener('dragover', (event) => {
  event.preventDefault()
  setDropZoneActive(true)
})

dropZone.addEventListener('dragleave', () => {
  setDropZoneActive(false)
})

dropZone.addEventListener('drop', async (event) => {
  event.preventDefault()
  setDropZoneActive(false)
  await renderFromFiles(event.dataTransfer.files)
})

fileInput.addEventListener('change', async (event) => {
  const files = event.target.files
  if (files?.length) {
    await renderFromFiles(files)
  }
  fileInput.value = ''
})

window.addEventListener('dragenter', (event) => {
  if (!hasFiles(event)) return
  event.preventDefault()
  state.dragDepth += 1
  globalDropTip.classList.add('visible')
})

window.addEventListener('dragover', (event) => {
  if (!hasFiles(event)) return
  event.preventDefault()
})

window.addEventListener('dragleave', (event) => {
  if (!hasFiles(event)) return
  event.preventDefault()
  state.dragDepth = Math.max(0, state.dragDepth - 1)
  if (state.dragDepth === 0) {
    globalDropTip.classList.remove('visible')
  }
})

window.addEventListener('drop', async (event) => {
  if (!hasFiles(event)) return
  event.preventDefault()
  state.dragDepth = 0
  globalDropTip.classList.remove('visible')

  if (event.dataTransfer.files?.length) {
    await renderFromFiles(event.dataTransfer.files)
  }
})

renderDefaultDoc()
