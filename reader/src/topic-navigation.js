export function relatedTopicLinks(path,cases) {
  const topic = path.split('/').pop()
  const owner=cases.find(c=>c.documents.includes(path))
  const background=owner?.researchType==='background' ? owner : cases.find(c=>c.id===owner?.backgroundCaseId)
  const backgroundPath=background?.documents.find(p=>p.endsWith('/'+topic))
  if (!backgroundPath || ['阅读入口.md','出处验证记录.md'].includes(topic)) return []
  if (!background.documents.includes(path) && !cases.some(c=>Object.values(c.topicDocuments||{}).includes(path))) return []
  const links=[{case:background,path:backgroundPath,label:'制度背景'}]
  for (const c of cases.filter(c=>c.backgroundCaseId===background.id)) {
    const label=(c.shortTitle||c.title)+'个案'
    const target=c?.topicDocuments?.[topic.replace(/\.md$/,'')]
    if(target)links.push({case:c,path:target,label})
  }
  return links.length>1 ? links.map(link=>({...link,current:link.path===path})) : []
}

export function mountTopicLinks(root,links,onRead) {
  root.querySelector('.topic-navigation')?.remove()
  if(!links.length)return
  const nav=root.ownerDocument.createElement('nav')
  nav.className='topic-navigation';nav.setAttribute('aria-label','同一专题的背景与三朝个案')
  for(const link of links){
    const a=root.ownerDocument.createElement('a')
    a.textContent=link.label
    a.href='#'+new URLSearchParams({case:link.case.id,doc:link.path})
    if(link.current)a.setAttribute('aria-current','page')
    a.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();onRead(link.case,link.path)})
    nav.append(a)
  }
  const heading=root.querySelector('h1')
  if(heading)heading.after(nav);else root.prepend(nav)
}
