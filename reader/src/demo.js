import { createMarkdownDocsFromModules, createMarkdownEngine } from './index.js'

const markdownModules = import.meta.glob('/data/md/*.md', {
  eager: true,
  query: '?raw',
  import: 'default'
})

const docs = createMarkdownDocsFromModules(markdownModules)

createMarkdownEngine({
  container: '#app',
  docs,
  defaultDocId: '/data/md/影像处理总结.md'
})
