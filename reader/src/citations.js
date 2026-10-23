export function localSourceLink(href, sources) {
  try {
    if (href.startsWith('hanji://')) {
      const url = new URL(href)
      // URL hostnames are normalized to lowercase, so resolve IDs case-insensitively.
      const host = decodeURIComponent(url.hostname).toLowerCase()
      const id = Object.keys(sources).find(k => k.toLowerCase() === host)
      return id ? { id, query: url.searchParams.get('q') } : null
    }
    const url = new URL(href, 'http://reader.local')
    if (url.hostname !== 'zh.wikisource.org') return null
    const path = decodeURIComponent(url.pathname)
    const match = path.match(/(?:舊唐書|新唐書|資治通鑑)\/卷(\d+)(上|下)?$/)
    if (!match) return null
    const book = path.includes('舊唐書') ? '旧唐书' : path.includes('新唐書') ? '新唐书' : '资治通鉴'
    const volume = String(Number(match[1])) + (match[2] || '')
    const id = Object.keys(sources).find(k => sources[k].book === book && sources[k].volume === volume)
    return id ? { id, query: null } : null
  } catch { return null }
}

export function resolveDocPath(current, href) {
  const url = new URL(href, `http://reader.local/${current}`)
  return { path: decodeURIComponent(url.pathname.slice(1)), hash: decodeURIComponent(url.hash.slice(1)) }
}

// Resolve against all registered cases, while keeping arbitrary workspace paths closed.
export function resolveDocumentLink(current, href, cases, currentCaseId) {
  if (!href || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')) return null
  let target
  try { target = resolveDocPath(current, href) } catch { return null }
  const owners = cases.filter(c => c.documents.includes(target.path))
  const owner = owners.find(c => c.id === currentCaseId) || (owners.length === 1 ? owners[0] : null)
  return owner ? {case:owner,...target} : null
}
