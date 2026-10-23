export function relatedTopicLinks(path,cases) {
  const topic = path.split('/').pop()
  const background=cases.find(c=>c.id==='late-tang-background')
  const backgroundPath=background?.documents.find(p=>p.endsWith('/'+topic))
  if (!backgroundPath || ['阅读入口.md','出处验证记录.md'].includes(topic)) return []
  if (!path.includes('/文化制度以及影响研究/') && !background.documents.includes(path)) return []
  const links=[{case:background,path:backgroundPath,label:'制度背景'}]
  for (const [id,label] of [['tang-xuanzong','宣宗个案'],['tang-yizong','懿宗个案'],['tang-xizong','僖宗个案']]) {
    const c=cases.find(c=>c.id===id)
    const target=c?.documents.find(p=>p.endsWith('/文化制度以及影响研究/'+topic))
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
