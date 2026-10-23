export function resolveReaderRoute(hash, cases, docs) {
  const raw = hash.replace(/^#/, '')
  const params = new URLSearchParams(raw)
  const selected = cases.find(c=>c.id === params.get('case'))
  const requested = params.get('doc') || selected?.entry
  const path = selected?.legacyPaths?.[requested] || requested
  if (selected && selected.documents.includes(path)) {
    return {case:selected,path,anchor:params.get('anchor') || ''}
  }
  let fragment
  try { fragment = decodeURIComponent(raw) } catch { return null }
  const match = fragment.match(/^footnote-(?:ref-)?(.+)$/)
  if (!match) return null
  const candidates = docs.filter(d=>d.content.includes(`[^${match[1]}]:`))
    .flatMap(d=>cases.filter(c=>c.documents.includes(d.path)).map(c=>({case:c,path:d.path,anchor:fragment})))
  return candidates.length === 1 ? candidates[0] : null
}

export function findReaderAnchor(root, fragment) {
  const raw = fragment.replace(/^#/, '')
  let decoded = raw
  try { decoded = decodeURIComponent(raw) } catch { /* try exact malformed ID */ }
  const ids = [raw,decoded]
  const footnote = decoded.match(/^(footnote-(?:ref-)?)(.+)$/)
  if (footnote) ids.push(footnote[1]+encodeURIComponent(footnote[2]))
  return ids.map(id=>root.getElementById(id)).find(Boolean) || null
}

export function scrollReaderAnchor(root, fragment) {
  const node = findReaderAnchor(root,fragment)
  if (!node) return false
  const content = root.getElementById('content')
  if (content?.contains(node)) {
    content.scrollTo({top:Math.max(0,content.scrollTop+node.getBoundingClientRect().top-
      content.getBoundingClientRect().top-24),behavior:'auto'})
  } else node.scrollIntoView({block:'start'})
  return true
}
