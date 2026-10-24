const categories=[['background','背景综述'],['era-topic','时代专题'],['dynasty','王朝资料']]

export function createDocumentTree(cases,onRead,{currentPath='',onSelectCase,expanded=new Set(),expandMatches=false,allCases=cases,onClearFilters}={}) {
  const doc=document
  const nav=doc.createElement('nav');nav.className='document-tree';nav.setAttribute('aria-label','文档分类目录')
  function branch(label,key,active=false) {
    const node=doc.createElement('details');node.dataset.treeKey=key
    node.open=active||(expandMatches&&!key.startsWith('group:'))||expanded.has(key)
    const summary=doc.createElement('summary');summary.textContent=label;node.append(summary)
    node.addEventListener('toggle',()=>{if(node.open)expanded.add(key);else expanded.delete(key)})
    return node
  }
  function action(label,fn,cls) {
    const button=doc.createElement('button');button.type='button';button.className=cls
    button.textContent=label;button.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();fn()})
    return button
  }
  const caseKind=c=>c.kind||(c.layoutVersion?'dynasty':c.researchType==='background'?'background':'era-topic')
  for(const [kind,label] of categories){
    const members=cases.filter(c=>caseKind(c)===kind)
    const total=allCases.filter(c=>caseKind(c)===kind)
    const category=branch(label,'category:'+kind,members.some(c=>c.documents.includes(currentPath)))
    category.className='tree-category';category.dataset.kind=kind
    const count=doc.createElement('span');count.className='tree-count';count.textContent=members.length===total.length?String(members.length):`${members.length} / ${total.length}`
    count.title=`当前匹配 ${members.length} 个，已登记 ${total.length} 个，共 ${total.reduce((n,c)=>n+c.documents.length,0)} 篇文稿`
    category.firstElementChild.append(count)
    if(!members.length){
      const empty=doc.createElement('p');empty.className='tree-empty'
      empty.textContent=total.length?`当前筛选无匹配结果；此类已登记 ${total.length} 个案例、${total.reduce((n,c)=>n+c.documents.length,0)} 篇文稿。`:'暂无已发布文稿'
      category.append(empty)
      if(total.length&&onClearFilters)category.append(action('清除筛选，查看文稿',onClearFilters,'case-overview'))
    }
    for(const c of members){
      const item=branch(c.title,'case:'+c.id,c.documents.includes(currentPath));item.className='tree-case';item.dataset.caseId=c.id
      if(onSelectCase)item.append(action('概览与纪年',()=>onSelectCase(c),'case-overview'))
      const groups=c.documentGroups?.length?c.documentGroups:[{title:'文稿',documents:c.documents}]
      for(const [i,g] of groups.entries()){
        const group=branch(g.title,'group:'+c.id+':'+i,g.documents.includes(currentPath));group.className='tree-group'
        for(const path of g.documents){
          const leaf=action(path.split('/').pop().replace(/\.md$/,''),()=>onRead(c,path),'tree-document')
          leaf.dataset.doc=path
          if(path===currentPath){leaf.classList.add('is-current');leaf.setAttribute('aria-current','page')}
          group.append(leaf)
        }
        item.append(group)
      }
      category.append(item)
    }
    nav.append(category)
  }
  return nav
}
