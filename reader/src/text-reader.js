// Plain text rendering only. Corpus strings never become HTML.
export function renderChapterText(root, text, query='') {
  root.replaceChildren()
  if (text == null) { root.textContent='原记录无正文。'; return }
  if (!query) { root.textContent=text; return }
  let start=0, index
  while ((index=text.indexOf(query,start))>=0) {
    root.append(text.slice(start,index))
    const mark=root.ownerDocument.createElement('mark');mark.textContent=query;root.append(mark)
    start=index+query.length
  }
  root.append(text.slice(start))
}

export function mountTextReader(request) {
  const $=id=>document.getElementById(id)
  let chapter=null, characterView=null, requestId=0, searchOffset=0
  const status=message=>$('text-status').textContent=message
  const open=()=>{if (!$('text-dialog').open)$('text-dialog').showModal()}
  function selectBook(id) {$('text-book').value=id||''}
  async function loadBooks() {
    const all=[]
    for(let offset=0;offset<100000;offset+=200){
      const rows=await request(`/api/text/books?limit=200&offset=${offset}`)
      all.push(...rows);if(rows.length<200)break
    }
    const previous=$('text-book').value
    $('text-book').replaceChildren(new Option('全部书目',''))
    for(const b of all)$('text-book').append(new Option(`${b.title} · ${b.book_id}`,b.book_id))
    selectBook(previous)
    return all
  }
  function clearChapter() {
    chapter=null;characterView=null
    for(const id of ['text-body','text-evidence','text-notes','text-assets'])$(id).replaceChildren()
    $('text-reading').checked=false;$('text-reading').disabled=true
  }
  async function readChapter(id,query='') {
    open();const generation=++requestId;clearChapter();status('读取数据库原文…')
    try {
      const row=await request(`/api/text/chapters/${encodeURIComponent(id)}`)
      if(generation!==requestId)return
      chapter=row;$('text-title').textContent=row.book_title+' · '+row.display_title
      $('text-evidence').textContent=`${row.chapter_id} · ${row.verification_status} · ${row.decoder}\n来源 SHA256 ${row.source_sha256}`
      renderChapterText($('text-body'),row.original_text,query)
      $('text-body').querySelector('mark')?.scrollIntoView?.({block:'center'})
      status('已读取数据库原文；解码状态不代表逐字校勘。')
      const results=await Promise.allSettled([
        request(`/api/text/chapters/${encodeURIComponent(id)}/characters`),
        request(`/api/text/chapters/${encodeURIComponent(id)}/assets`)
      ])
      if(generation!==requestId)return
      const [characters,assets]=results
      if(characters.status==='fulfilled'){
        characterView=characters.value
        $('text-reading').disabled=!characterView.replacements_applied
        const notes=characterView.notes||[]
        $('text-notes').append(Object.assign(document.createElement('p'),{textContent:`特殊字记录 ${notes.length} 处；已核编码映射 ${characterView.replacements_applied} 处；待核 ${characterView.unresolved_occurrences||0} 处。`}))
        for(const n of notes){
          const item=document.createElement('p')
          item.textContent=`字位 ${n.offset} · ${n.codepoint} · ${n.font_trace?.font_description||'字体待核'} · ${n.replacement?'阅读映射 → '+n.replacement:'待核，保留原码位'}`
          $('text-notes').append(item)
        }
      }else $('text-notes').textContent='字符记录读取失败：'+characters.reason.message
      if(assets.status==='fulfilled'){
        const items=assets.value.items||[]
        $('text-assets').append(Object.assign(document.createElement('p'),{textContent:`图文资源 ${items.length} 项；可能包含同一图像的备用格式。`}))
        for(const a of items){
          const p=document.createElement('p');p.textContent=`${a.ordinal} · ${a.kind} · ${a.format} · RTF字节 ${a.start_byte}—${a.end_byte} `
          for(const [part,label] of [['raw','原始分组'],...(a.payload_size?[['payload','图片数据']]:[])]){
            const link=document.createElement('a');link.textContent=label;link.href=`/api/text/chapters/${encodeURIComponent(id)}/assets/${a.ordinal}/download?part=${part}`
            link.download='';p.append(link,document.createTextNode(' '))
          }
          $('text-assets').append(p)
        }
      }else $('text-assets').textContent='资源读取失败：'+assets.reason.message
    }catch(e){if(generation===requestId)status(e.message)}
  }
  async function search(reset=true){
    if(reset)searchOffset=0
    const query=$('text-query').value.trim();if(!query){status('请输入检索词。');return}
    const generation=++requestId;clearChapter();status('检索数据库原文…')
    const params=new URLSearchParams({q:query,limit:20,offset:searchOffset})
    if($('text-book').value)params.set('book_id',$('text-book').value)
    try{
      const data=await request('/api/text/search?'+params)
      if(generation!==requestId)return
      $('text-results').replaceChildren();$('text-title').textContent='原文检索结果'
      $('text-next').disabled=!data.has_more;$('text-prev').disabled=searchOffset===0
      for(const row of data.items){
        const item=document.createElement('article'),button=document.createElement('button'),excerpt=document.createElement('p')
        button.textContent=`${row.book_title} · ${row.display_title} · 段 ${row.ordinal}`
        button.addEventListener('click',()=>readChapter(row.chapter_id,query))
        const pos=row.original_text.indexOf(query),left=Math.max(0,pos-70)
        renderChapterText(excerpt,row.original_text.slice(left,left+240),query)
        item.append(button,excerpt);$('text-results').append(item)
      }
      status(`${data.items.length} 条 · 第 ${searchOffset/20+1} 页。点击结果读取整章；检索保留原文标点，不跨段匹配。`)
    }catch(e){if(generation===requestId)status(e.message)}
  }
  async function browse(){
    const id=$('text-book').value;if(!id){status('请先选择一本书。');return}
    const generation=++requestId;clearChapter();$('text-results').replaceChildren();status('读取篇章目录…')
    try{
      let count=0
      for(let offset=0;offset<100000;offset+=500){
        const rows=await request(`/api/text/books/${encodeURIComponent(id)}/chapters?limit=500&offset=${offset}`)
        if(generation!==requestId)return
        for(const row of rows){const button=document.createElement('button');button.textContent=row.display_title;button.addEventListener('click',()=>readChapter(row.chapter_id));$('text-results').append(button);count++}
        if(rows.length<500)break
      }
      status(`${count} 个章节，点击读取数据库正文。`)
    }catch(e){if(generation===requestId)status(e.message)}
  }
  $('text-form').addEventListener('submit',e=>{e.preventDefault();search()})
  $('text-prev').addEventListener('click',()=>{searchOffset=Math.max(0,searchOffset-20);search(false)})
  $('text-next').addEventListener('click',()=>{searchOffset+=20;search(false)})
  $('text-browse').addEventListener('click',browse)
  $('text-reading').addEventListener('change',()=>{
    if(!chapter)return
    renderChapterText($('text-body'),$('text-reading').checked?characterView.reading_text:chapter.original_text,$('text-query').value.trim())
  })
  return {
    async show(){open();try{await loadBooks();status('原文库已连接。可选书检索，或浏览篇章。')}catch(e){status(e.message)}},
    async source(id,query=''){
      open();status('定位已登记出处…')
      try{
        const source=await request(`/api/text/source/${encodeURIComponent(id)}`)
        await loadBooks()
        $('text-query').value=query;selectBook(source.bookId)
        await readChapter(source.chapterId,query)
      }catch(e){status(e.message)}
    },
    readChapter,
    async health(){const data=await request('/api/text/health');return data.status==='ok'}
  }
}
