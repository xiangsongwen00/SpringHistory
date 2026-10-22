# makeDocs 历史资料制作

这里是 Agent 的制作工作区；阅读器只读取 `docs/`。先读 [制作规则](AGENTS.md)，再使用模板建立案例。

在项目根目录执行：

```powershell
python makeDocs/query_text.py --book-id B01-137 --query 五年内不加税赋
python makeDocs/query_text.py --chapter B01-137:20
python makeDocs/query_source.py J18
python makeDocs/query_source.py J18 --query 五年内不加税赋 --open
python makeDocs/validate_docs.py
```

`query_text.py` 使用独立原文服务 `http://127.0.0.1:18866`，按书目ID检索段落，再按实际章ID读取完整上下文；先双击根目录“启动原文查询服务.cmd”。输出保留查询时间、出处哈希、解码器和核验状态，可用`--output`保存证据JSON；含原文的批量结果留本机，不直接上传，正式整理稿仍只写docs。`HISTORY_API_BASE`可指定其他部署。书目版本信息尚未完整结构化，引用时另核原库版本资料。

`query_source.py` 不加--open仅检查目录与目标卷章；加--open使用 `http://127.0.0.1:18865` 阅读服务操作汉籍，默认等待120秒，`--timeout 180`可调整。它用于新库不可用或需要原始字形的场景。失败或超时会返回非零退出码，不从`done`推导原文已校勘。

校验工具只读，不自动改稿；检查案例入口/文档目标、脚注、`hanji://` 出处登记及本地链接范围。退出码 0 表示这些结构检查通过，不代表历史内容正确。`--json` 输出机器可读诊断。

案例示例结构：

```text
docs/cases/<case-id>/
  入口.md
  编年.md
  纪传.md
  历史地理.md
  史料与待考.md
  核验记录.md
```

`docs/cases.json` 可按以下格式登记。`entry` 与每项 `years.doc` 都必须属于本案例的 `documents`；分期 ID 唯一，起止年不能颠倒，也不能超出案例范围。导航年份须为案例范围内的整数。

```json
{
  "cases": [{
    "id": "tang-xuanzong",
    "title": "唐宣宗资料",
    "period": "晚唐",
    "startYear": 846,
    "endYear": 859,
    "entry": "docs/cases/tang-xuanzong/入口.md",
    "documents": [
      "docs/cases/tang-xuanzong/入口.md",
      "docs/cases/tang-xuanzong/编年.md"
    ],
    "topics": ["方镇", "历史地理"],
    "sections": [{
      "id": "early",
      "title": "即位与河陇经营",
      "startYear": 846,
      "endYear": 850
    }],
    "years": [{
      "year": 846,
      "label": "会昌六年",
      "doc": "docs/cases/tang-xuanzong/编年.md",
      "anchor": "year-846"
    }]
  }]
}
```

使用年度锚点时，在目标文档相应标题前写 `<a id="year-846"></a>`。校验器也支持阅读器当前生成的 `heading-1`、`heading-2` 等标题锚点（包含 ATX、Setext 与 HTML 标题）；调整标题顺序会改变这些编号，因此年度导航优先采用显式 ID。`anchor` 如填写就必须真实存在，不能只在清单里声明。
