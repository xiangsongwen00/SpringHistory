export function filterCases(cases, {keyword='', period='', year=''}={}) {
  const q = keyword.trim().toLowerCase()
  return cases.filter(c => (!period || c.period === period) &&
    (year === '' || (Number(year) >= c.startYear && Number(year) <= c.endYear)) &&
    (!q || [c.title,c.description,c.period,...(c.topics||[])].join(' ').toLowerCase().includes(q)))
}

const el = (tag, text, cls) => {
  const node = document.createElement(tag)
  if (text != null) node.textContent = text
  if (cls) node.className = cls
  return node
}
const button = (text, action) => {
  const node = el('button', text)
  node.type = 'button'; node.addEventListener('click', action)
  return node
}

export function mountCaseHub(cases, onRead) {
  const grid = document.getElementById('case-grid')
  const detail = document.getElementById('case-detail')
  const search = document.getElementById('case-search')
  const period = document.getElementById('case-period')
  const year = document.getElementById('case-year')
  for (const value of [...new Set(cases.map(c=>c.period))]) {
    const option = el('option', value); option.value = value; period.append(option)
  }
  function showCase(c) {
    detail.hidden = false; detail.replaceChildren()
    detail.append(el('p', `${c.period} · ${c.startYear}—${c.endYear} · ${c.status}`, 'eyebrow'), el('h2', c.title))
    detail.append(button('阅读案例导读', ()=>onRead(c,c.entry)))
    const stageBar = el('div', null, 'stage-bar')
    const years = el('div', null, 'year-grid')
    const summary = el('p', '选择分期可缩小纪年范围；专题文稿可能跨越多个分期。', 'hub-note')
    function showYears(section) {
      years.replaceChildren()
      for (const y of c.years || []) {
        if (section && (y.year < section.startYear || y.year > section.endYear)) continue
        years.append(button(`${y.year} · ${y.label}`, ()=>onRead(c,y.doc,y.anchor)))
      }
      summary.textContent = section ? section.description : '全部纪年；专题文稿可能跨越多个分期。'
      for (const b of stageBar.children) b.setAttribute('aria-pressed', String(b.dataset.section === (section?.id || '')))
    }
    const all = button('全部分期', ()=>showYears(null)); all.dataset.section = ''; stageBar.append(all)
    for (const section of c.sections || []) {
      const b = button(`${section.startYear}—${section.endYear} ${section.title}`, ()=>showYears(section))
      b.dataset.section = section.id; stageBar.append(b)
    }
    detail.append(el('h3','按事件分期与纪年进入'),stageBar,summary,years)
    const list = el('div',null,'document-grid')
    for (const path of c.documents) {
      list.append(button(path.split('/').pop().replace(/\.md$/,''),()=>onRead(c,path)))
    }
    detail.append(el('h3','案例文稿'),list)
    showYears(null)
    detail.scrollIntoView?.({behavior:'smooth',block:'start'})
  }
  function render() {
    detail.hidden = true; grid.replaceChildren()
    const matches = filterCases(cases,{keyword:search.value,period:period.value,year:year.value})
    document.getElementById('case-count').textContent = `${matches.length} 个案例 · 共 ${cases.length} 个已登记案例`
    for (const c of matches) {
      const card = el('article',null,'case-card')
      card.append(el('p',`${c.period} / ${c.startYear}—${c.endYear}`,'eyebrow'),
        el('h2',c.title),el('p',c.description),el('p',(c.topics||[]).join(' · '),'hub-note'),
        button('选择案例与纪年 →',()=>showCase(c)))
      grid.append(card)
    }
    if (!matches.length) grid.append(el('p','没有符合条件的案例，请调整时期、年份或关键词。'))
  }
  for (const input of [search,period,year]) input.addEventListener('input',render)
  render()
  return {showCase}
}
