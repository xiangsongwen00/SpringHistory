/*
 * @File: src/mermaidZoom.js
 * @Description: Mermaid 图表缩放/拖拽/导出能力
 */

const ZOOM_CONFIG = {
  minScale: 0.3,
  maxScale: 4,
  scaleStep: 0.1,
  transitionDuration: 0,
  fitPadding: 16
}

let observer = null

export function fitAllMermaidToDiagram(root = document) {
  const wrappers = Array.from(root.querySelectorAll('.mermaid-zoom-wrapper'))
  wrappers.forEach((wrapper) => {
    wrapper.__mermaidZoomController?.zoomToDiagram?.()
  })
}

export function fillAllMermaidToCanvas(root = document) {
  const wrappers = Array.from(root.querySelectorAll('.mermaid-zoom-wrapper'))
  wrappers.forEach((wrapper) => {
    wrapper.__mermaidZoomController?.fillCanvas?.()
  })
}

export function refreshAllMermaidOverlays(root = document) {
  const wrappers = Array.from(root.querySelectorAll('.mermaid-zoom-wrapper'))
  wrappers.forEach((wrapper) => {
    wrapper.__mermaidZoomController?.refresh?.()
  })
}

export function initMermaidZoom() {
  if (!observer) {
    observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type !== 'childList') return
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== Node.ELEMENT_NODE) return
          const mermaidElements = node.classList?.contains('mermaid')
            ? [node]
            : node.querySelectorAll?.('.mermaid') || []

          mermaidElements.forEach((mermaidContainer) => {
            if (mermaidContainer.closest('.mermaid-zoom-wrapper')) return
            if (!mermaidContainer.dataset.zoomInitialized) {
              setupMermaidZoom(mermaidContainer)
            }
          })
        })
      })
    })

    observer.observe(document.body, {
      childList: true,
      subtree: true
    })
  }

  setTimeout(() => {
    document.querySelectorAll('.mermaid').forEach((mermaidContainer) => {
      if (mermaidContainer.closest('.mermaid-zoom-wrapper')) return
      if (!mermaidContainer.dataset.zoomInitialized) {
        setupMermaidZoom(mermaidContainer)
      }
    })
  }, 120)
}

function setupMermaidZoom(mermaidContainer) {
  if (mermaidContainer.closest('.mermaid-zoom-wrapper')) {
    mermaidContainer.dataset.zoomInitialized = 'true'
    return
  }
  const svg = mermaidContainer.querySelector('svg')
  if (!svg) {
    // Mermaid SVG 尚未渲染完成，等待下一次初始化尝试
    return
  }

  const wrapper = document.createElement('div')
  wrapper.className = 'mermaid-zoom-wrapper'

  const controls = document.createElement('div')
  controls.className = 'mermaid-zoom-controls'
  controls.innerHTML = `
    <button class="zoom-btn zoom-in" title="放大" type="button">+</button>
    <button class="zoom-btn zoom-out" title="缩小" type="button">-</button>
    <button class="zoom-btn zoom-reset" title="重置" type="button">R</button>
    <button class="zoom-btn zoom-fit" title="缩放至流程图" type="button">S</button>
    <button class="zoom-btn zoom-fill" title="流程图填充画布" type="button">F</button>
    <button class="zoom-btn zoom-center" title="居中" type="button">C</button>
    <button class="zoom-btn zoom-export" title="导出图片" type="button">E</button>
    <span class="zoom-level">100%</span>
  `

  const frame = document.createElement('div')
  frame.className = 'mermaid-focus-frame'
  const guides = document.createElement('div')
  guides.className = 'mermaid-canvas-guides'

  mermaidContainer.parentNode.insertBefore(wrapper, mermaidContainer)
  wrapper.appendChild(mermaidContainer)
  wrapper.appendChild(frame)
  wrapper.appendChild(guides)
  wrapper.appendChild(controls)

  mermaidContainer.dataset.zoomInitialized = 'true'

  let layoutObserver = null

  let scale = 1
  let translateX = 0
  let translateY = 0
  let isDragging = false
  let startX = 0
  let startY = 0

  svg.style.transformOrigin = '0 0'
  svg.style.transition = `transform ${ZOOM_CONFIG.transitionDuration}ms ease`
  svg.style.cursor = 'grab'
  svg.style.userSelect = 'none'

  const zoomLevel = controls.querySelector('.zoom-level')
  const envelopePadding = 8

  function updateTransform() {
    svg.style.transform = `matrix(${scale}, 0, 0, ${scale}, ${translateX}, ${translateY})`
    if (zoomLevel) {
      zoomLevel.textContent = `${Math.round(scale * 100)}%`
    }
    syncFocusFrame()
    syncCanvasGuides()
    evaluateAlignment()
  }

  function runWithoutTransition(callback) {
    const previousTransition = svg.style.transition
    svg.style.transition = 'none'
    callback()
    // 强制浏览器刷新，确保 transform 已提交
    void svg.getBoundingClientRect()
    svg.style.transition = previousTransition
  }

  function getGraphBoundsInWrapper() {
    const wrapperRect = wrapper.getBoundingClientRect()
    const candidates = Array.from(
      svg.querySelectorAll('.node, .cluster, .edgePath, .edgeLabel, .flowchart-link, .label')
    )

    let minLeft = Number.POSITIVE_INFINITY
    let minTop = Number.POSITIVE_INFINITY
    let maxRight = Number.NEGATIVE_INFINITY
    let maxBottom = Number.NEGATIVE_INFINITY

    for (const el of candidates) {
      const rect = el.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      minLeft = Math.min(minLeft, rect.left)
      minTop = Math.min(minTop, rect.top)
      maxRight = Math.max(maxRight, rect.right)
      maxBottom = Math.max(maxBottom, rect.bottom)
    }

    if (!Number.isFinite(minLeft) || !Number.isFinite(minTop)) {
      return null
    }

    return {
      left: minLeft - wrapperRect.left,
      top: minTop - wrapperRect.top,
      width: maxRight - minLeft,
      height: maxBottom - minTop
    }
  }

  function getViewportBoundsInWrapper() {
    const wrapperRect = wrapper.getBoundingClientRect()
    const containerRect = mermaidContainer.getBoundingClientRect()
    const styles = getComputedStyle(mermaidContainer)

    const padLeft = parseFloat(styles.paddingLeft) || 0
    const padRight = parseFloat(styles.paddingRight) || 0
    const padTop = parseFloat(styles.paddingTop) || 0
    const padBottom = parseFloat(styles.paddingBottom) || 0

    const left = containerRect.left - wrapperRect.left + padLeft
    const top = containerRect.top - wrapperRect.top + padTop
    const width = Math.max(20, containerRect.width - padLeft - padRight)
    const height = Math.max(20, containerRect.height - padTop - padBottom)

    return { left, top, width, height }
  }

  function syncFocusFrame() {
    const graph = getGraphBoundsInWrapper()
    if (!graph || graph.width <= 0 || graph.height <= 0) {
      frame.style.display = 'none'
      return
    }

    frame.style.display = 'block'
    frame.style.left = `${Math.round(graph.left - envelopePadding)}px`
    frame.style.top = `${Math.round(graph.top - envelopePadding)}px`
    frame.style.width = `${Math.round(graph.width + envelopePadding * 2)}px`
    frame.style.height = `${Math.round(graph.height + envelopePadding * 2)}px`
  }

  function syncCanvasGuides() {
    const viewport = getViewportBoundsInWrapper()
    guides.style.left = `${Math.round(viewport.left)}px`
    guides.style.top = `${Math.round(viewport.top)}px`
    guides.style.width = `${Math.round(viewport.width)}px`
    guides.style.height = `${Math.round(viewport.height)}px`
  }

  function getRectCenterInWrapper(el) {
    const wrapperRect = wrapper.getBoundingClientRect()
    const rect = el.getBoundingClientRect()
    return {
      x: rect.left - wrapperRect.left + rect.width / 2,
      y: rect.top - wrapperRect.top + rect.height / 2
    }
  }

  function evaluateAlignment() {
    if (frame.style.display === 'none') {
      wrapper.classList.remove('alignment-ok')
      wrapper.removeAttribute('data-align-dx')
      wrapper.removeAttribute('data-align-dy')
      return
    }

    const frameCenter = getRectCenterInWrapper(frame)
    const guideCenter = getRectCenterInWrapper(guides)
    const dx = frameCenter.x - guideCenter.x
    const dy = frameCenter.y - guideCenter.y

    wrapper.dataset.alignDx = dx.toFixed(2)
    wrapper.dataset.alignDy = dy.toFixed(2)

    const threshold = 1.5
    const aligned = Math.abs(dx) <= threshold && Math.abs(dy) <= threshold
    wrapper.classList.toggle('alignment-ok', aligned)
  }

  function getFrameBoundsInWrapper() {
    return getViewportBoundsInWrapper()
  }

  function zoom(delta, clientX, clientY) {
    const oldScale = scale
    scale = Math.max(ZOOM_CONFIG.minScale, Math.min(ZOOM_CONFIG.maxScale, scale + delta))

    if (clientX !== undefined && clientY !== undefined) {
      const wrapperRect = wrapper.getBoundingClientRect()
      const mouseX = clientX - wrapperRect.left
      const mouseY = clientY - wrapperRect.top

      const svgX = (mouseX - translateX) / oldScale
      const svgY = (mouseY - translateY) / oldScale

      translateX = mouseX - svgX * scale
      translateY = mouseY - svgY * scale
    }

    updateTransform()
  }

  function resetZoom() {
    scale = 1
    translateX = 0
    translateY = 0
    updateTransform()
  }

  function centerGraph() {
    const graphBounds = getGraphBoundsInWrapper()
    const frameBounds = getFrameBoundsInWrapper()
    if (!graphBounds || graphBounds.width <= 0 || graphBounds.height <= 0) {
      const wrapperRect = wrapper.getBoundingClientRect()
      const svgRect = svg.getBoundingClientRect()
      const rawWidth = svgRect.width / scale
      const rawHeight = svgRect.height / scale
      translateX = (wrapperRect.width - rawWidth * scale) / 2
      translateY = (wrapperRect.height - rawHeight * scale) / 2
      updateTransform()
      return
    }

    const frameCenterX = frameBounds.left + frameBounds.width / 2
    const frameCenterY = frameBounds.top + frameBounds.height / 2
    const graphCenterX = graphBounds.left + graphBounds.width / 2
    const graphCenterY = graphBounds.top + graphBounds.height / 2

    // 始终按当前屏幕坐标差值做平移对齐，缩放后同样稳定
    translateX += frameCenterX - graphCenterX
    translateY += frameCenterY - graphCenterY
    updateTransform()
  }

  function centerGraphStable() {
    syncFocusFrame()
    syncCanvasGuides()
    centerGraph()
    // 二次立即校准，消除小数像素误差
    centerGraph()
  }

  function getBaseGraphBounds() {
    const previousScale = scale
    const previousTranslateX = translateX
    const previousTranslateY = translateY
    let graphBounds = null
    runWithoutTransition(() => {
      scale = 1
      translateX = 0
      translateY = 0
      updateTransform()
      graphBounds = getGraphBoundsInWrapper()
      scale = previousScale
      translateX = previousTranslateX
      translateY = previousTranslateY
      updateTransform()
    })
    return graphBounds
  }

  function applyScaleToCenterGraph(nextScale) {
    scale = Math.max(ZOOM_CONFIG.minScale, Math.min(ZOOM_CONFIG.maxScale, nextScale))
    updateTransform()
    // 缩放后用当前包络中心与画布中心对齐
    centerGraphStable()
  }

  function computeContainScale(graphBounds, frameBounds) {
    const safeWidth = Math.max(20, frameBounds.width - ZOOM_CONFIG.fitPadding * 2)
    const safeHeight = Math.max(20, frameBounds.height - ZOOM_CONFIG.fitPadding * 2)
    return Math.min(
      ZOOM_CONFIG.maxScale,
      Math.max(
        ZOOM_CONFIG.minScale,
        Math.min(safeWidth / graphBounds.width, safeHeight / graphBounds.height)
      )
    )
  }

  function fillCanvas() {
    syncFocusFrame()
    const graphBounds = getBaseGraphBounds()
    const frameBounds = getFrameBoundsInWrapper()
    if (!graphBounds || graphBounds.width <= 0 || graphBounds.height <= 0) {
      centerGraph()
      return
    }
    const containScale = computeContainScale(graphBounds, frameBounds)
    applyScaleToCenterGraph(containScale)
  }

  function zoomToDiagram() {
    syncFocusFrame()
    const previousScale = scale
    const graphBounds = getBaseGraphBounds()
    const frameBounds = getFrameBoundsInWrapper()
    if (!graphBounds || graphBounds.width <= 0 || graphBounds.height <= 0) {
      centerGraph()
      return
    }

    const containScale = computeContainScale(graphBounds, frameBounds)
    const adaptiveScale = Math.min(previousScale, containScale)
    applyScaleToCenterGraph(adaptiveScale)
  }

  function isCompositeDiagram() {
    const clusterCount = svg.querySelectorAll('.cluster').length
    const nodeCount = svg.querySelectorAll('.node').length
    return clusterCount >= 3 || nodeCount >= 36
  }

  function computeExportScale(width, height, compositeMode = false) {
    const maxSidePx = compositeMode ? 4600 : 2800
    const minScale = compositeMode ? 2.4 : 2
    const maxScale = compositeMode ? 7 : 6
    const baseSide = Math.max(1, width, height)
    let exportScale = Math.max(minScale, Math.min(maxScale, maxSidePx / baseSide))

    const maxArea = 180000000
    const projectedArea = width * height * exportScale * exportScale
    if (projectedArea > maxArea) {
      exportScale = Math.max(1.4, Math.sqrt(maxArea / Math.max(1, width * height)))
    }
    return exportScale
  }

  async function exportImage() {
    const exportBtn = controls.querySelector('.zoom-export')
    if (!exportBtn) return

    const originalText = exportBtn.textContent
    exportBtn.textContent = '...'
    exportBtn.disabled = true

    try {
      const prev = { scale, translateX, translateY }
      const compositeMode = isCompositeDiagram()
      if (compositeMode) {
        runWithoutTransition(() => {
          scale = 1
          translateX = 0
          translateY = 0
          updateTransform()
        })
      } else {
        fillCanvas()
      }

      syncFocusFrame()
      syncCanvasGuides()
      evaluateAlignment()
      wrapper.classList.add('is-exporting-diagram')
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

      const target = compositeMode ? mermaidContainer : wrapper
      const targetRect = target.getBoundingClientRect()
      const frameRect = frame.getBoundingClientRect()
      const targetWidth = Math.max(target.scrollWidth, target.clientWidth, 1)
      const targetHeight = Math.max(target.scrollHeight, target.clientHeight, 1)

      const cropX = Math.max(0, Math.floor(frameRect.left - targetRect.left))
      const cropY = Math.max(0, Math.floor(frameRect.top - targetRect.top))
      const cropWidth = Math.max(1, Math.min(Math.ceil(frameRect.width), targetWidth - cropX))
      const cropHeight = Math.max(1, Math.min(Math.ceil(frameRect.height), targetHeight - cropY))

      const exportScale = computeExportScale(cropWidth, cropHeight, compositeMode)

      const { default: html2canvas } = await import('html2canvas')
      const canvas = await html2canvas(target, {
        scale: exportScale,
        useCORS: true,
        backgroundColor: '#ffffff',
        x: cropX,
        y: cropY,
        width: cropWidth,
        height: cropHeight,
        windowWidth: targetWidth,
        windowHeight: targetHeight
      })

      canvas.toBlob((blob) => {
        if (!blob) return
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `mermaid-diagram-${Date.now()}.png`
        document.body.appendChild(link)
        link.click()
        link.remove()
        URL.revokeObjectURL(url)
      }, 'image/png', 1)

      // 导出完成后恢复用户当前浏览状态
      runWithoutTransition(() => {
        scale = prev.scale
        translateX = prev.translateX
        translateY = prev.translateY
        updateTransform()
      })
    } catch (error) {
      console.error('导出 Mermaid 图表失败:', error)
    } finally {
      wrapper.classList.remove('is-exporting-diagram')
      exportBtn.textContent = originalText
      exportBtn.disabled = false
    }
  }

  wrapper.addEventListener('wheel', (event) => {
    event.preventDefault()
    const delta = event.deltaY > 0 ? -ZOOM_CONFIG.scaleStep : ZOOM_CONFIG.scaleStep
    zoom(delta, event.clientX, event.clientY)
  }, { passive: false })

  svg.addEventListener('mousedown', (event) => {
    if (event.button !== 0) return
    isDragging = true
    startX = event.clientX - translateX
    startY = event.clientY - translateY
    svg.style.cursor = 'grabbing'
    event.preventDefault()
  })

  document.addEventListener('mousemove', (event) => {
    if (!isDragging) return
    translateX = event.clientX - startX
    translateY = event.clientY - startY
    updateTransform()
  })

  document.addEventListener('mouseup', () => {
    if (!isDragging) return
    isDragging = false
    svg.style.cursor = 'grab'
  })

  controls.querySelector('.zoom-in')?.addEventListener('click', () => {
    const rect = wrapper.getBoundingClientRect()
    zoom(ZOOM_CONFIG.scaleStep * 2, rect.left + rect.width / 2, rect.top + rect.height / 2)
  })

  controls.querySelector('.zoom-out')?.addEventListener('click', () => {
    const rect = wrapper.getBoundingClientRect()
    zoom(-ZOOM_CONFIG.scaleStep * 2, rect.left + rect.width / 2, rect.top + rect.height / 2)
  })

  controls.querySelector('.zoom-reset')?.addEventListener('click', resetZoom)
  controls.querySelector('.zoom-fit')?.addEventListener('click', zoomToDiagram)
  controls.querySelector('.zoom-fill')?.addEventListener('click', fillCanvas)
  controls.querySelector('.zoom-center')?.addEventListener('click', centerGraphStable)
  controls.querySelector('.zoom-export')?.addEventListener('click', exportImage)

  svg.addEventListener('dblclick', resetZoom)

  wrapper.setAttribute('tabindex', '0')
  wrapper.addEventListener('keydown', (event) => {
    const rect = wrapper.getBoundingClientRect()
    if (event.key === 'c' || event.key === 'C') {
      centerGraphStable()
    } else if (event.key === 'r' || event.key === 'R') {
      resetZoom()
    } else if (event.key === 'e' || event.key === 'E') {
      exportImage()
    } else if (event.key === 's' || event.key === 'S') {
      zoomToDiagram()
    } else if (event.key === 'f' || event.key === 'F') {
      fillCanvas()
    } else if (event.key === '+' || event.key === '=') {
      zoom(ZOOM_CONFIG.scaleStep * 2, rect.left + rect.width / 2, rect.top + rect.height / 2)
    } else if (event.key === '-') {
      zoom(-ZOOM_CONFIG.scaleStep * 2, rect.left + rect.width / 2, rect.top + rect.height / 2)
    }
  })

  wrapper.__mermaidZoomController = {
    zoomToDiagram,
    fillCanvas,
    resetZoom,
    centerGraph: centerGraphStable,
    refresh() {
      syncFocusFrame()
      syncCanvasGuides()
      evaluateAlignment()
    }
  }

  setTimeout(zoomToDiagram, 80)

  const syncAndCenter = () => {
    syncFocusFrame()
    syncCanvasGuides()
    evaluateAlignment()
  }

  syncAndCenter()
  window.addEventListener('resize', syncAndCenter, { passive: true })

  if (typeof ResizeObserver !== 'undefined') {
    layoutObserver = new ResizeObserver(() => {
      syncFocusFrame()
      syncCanvasGuides()
      evaluateAlignment()
    })
    layoutObserver.observe(wrapper)
    layoutObserver.observe(mermaidContainer)
    layoutObserver.observe(svg)
  }

  wrapper.__mermaidZoomCleanup = () => {
    window.removeEventListener('resize', syncAndCenter)
    layoutObserver?.disconnect()
    layoutObserver = null
  }
}
