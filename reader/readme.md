<!--
 * @Author: yangjie
 * @Date: 2026-05-30 10:27:47
 * @LastEditors: yangjie 
 * @LastEditTime: 2026-06-08 21:28:05
 * @FilePath: \0-readmd\readme.md
 * @Description: 
 * 
 * Copyright (c) 2026 by bimcc, All Rights Reserved. 
-->
# read-markdown-engine 使用说明

`dist/` 目录下包含两个产物：

- `read-markdown-engine.mjs` — ESM 入口，导出 `createMarkdownEngine` 和 `createMarkdownDocsFromModules`
- `read-markdown-engine.css` — 引擎内置样式，需单独引入

## 1. 浏览器直接使用（推荐用于 demo）

```html
<link rel="stylesheet" href="./read-markdown-engine.css" />
<div id="app"></div>
<script type="module">
  import { createMarkdownEngine } from './read-markdown-engine.mjs'

  const docs = [
    {
      path: 'demo.md',
      label: '演示文档',
      content: '# Hello\n\n这是一个 Markdown 文档。'
    }
  ]

  createMarkdownEngine({
    container: '#app',
    docs,
    defaultDocId: 'demo.md'
  })
</script>
```

## 2. 在项目中通过包入口使用

当 `package.json` 的 `exports` 指向 `./dist/read-markdown-engine.mjs` 时，可直接：

```js
import { createMarkdownEngine, createMarkdownDocsFromModules } from 'read-markdown-engine'
import 'read-markdown-engine/dist/read-markdown-engine.css'
```

## 3. API 说明

### `createMarkdownEngine(options)`

创建并渲染 Markdown 阅读器，返回引擎实例。

`options`：

- `container`: `string | HTMLElement`，渲染容器（默认 `#app`）
- `docs`: `Array<{ path?: string; id?: string; label?: string; content: string }>`，文档列表
- `defaultDocId`: `string`，默认文档 `path`

返回实例方法：

- `render()`：重新渲染当前文档
- `setDocs(nextDocs, nextDefaultDocId?)`：替换文档并渲染
- `renderDocById(docId)`：切换指定文档并渲染，返回 `boolean`
- `getDocs()`：获取当前文档数组副本
- `getCurrentDoc()`：获取当前文档
- `destroy()`：销毁实例并清空容器

### `createMarkdownDocsFromModules(modules)`

把 `import.meta.glob` 的结果转换为 `docs` 结构。

```js
const modules = import.meta.glob('./docs/*.md', { eager: true, as: 'raw' })
const docs = createMarkdownDocsFromModules(modules)

createMarkdownEngine({
  container: '#app',
  docs,
  defaultDocId: docs[0]?.path
})
```

## 4. 注意事项

- 样式与 JS 分离打包，使用时需单独引入 `read-markdown-engine.css`。
- 使用 Mermaid 图表时，请确保在浏览器环境下运行（非 SSR）。
- 本地直接双击 `html` 可能受浏览器模块/CORS 限制，建议用本地静态服务器或 `vite preview` 打开。
