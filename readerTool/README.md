# readerTool：汉籍原文导出流水线

目标是把本机文献转换为可追溯的 UTF-8 文本，供 `myHistorySys` 入库。全程不打开旧程序窗口，不使用坐标、截图或剪贴板，不修改原书库。原书库、DLL、下载的运行时和导出的正文均不随开源仓库发布。

## 已验证的技术路径

`.CAL` 可读取书目；`.AMG` 是 `FTR_ARTI` 专有文章容器，不是直接可读的 TXT。当前调用安装目录自带的 **32 位 `Ftrquery.dll`** 取出文章 RTF，再转换为 Unicode。它解决了批量取文的问题，但**尚未独立实现 AMG 的压缩算法**。导出阶段仍需要本机 DLL；JSONL 导入 PostgreSQL 后，阅读、查询服务无需旧程序或 DLL。

在独立 x86 子进程中，以 cdecl 调用 `FTR_OpenArticleMgr`、`FTR_GetArticleInfo`、`FTR_GetArticleData`、`FTR_CloseArticleMgr`。已实测信息结构的标题偏移260、正文长度偏移520；取正文返回值是 BOOL，不是长度。文章数来自已验证容器头的偏移22。每本书单独进程，有超时、长度上限和格式检查，异常不能直接当成成功。

原 RTF 将 GBK 的部分尾字节直接写成 ASCII，普通 RTF 转换会拆坏双字节字符。本工具保留控制语法，把正文的字节文字规范为连续十六进制转义后解码。Python GBK 拒绝的有效二字节 GB18030 扩展，使用明确的错误处理器转换并逐种记录原字节和 Unicode 码位；其他错误仍隔离。私用区字符与图片/对象单独计数，不能据此声称已还原缺字字形、插图或版面。

遇到RTF原生脚注、批注或页眉页脚文本时先隔离，避免普通正文转换器静默丢弃这些文字。本次对全库原RTF补查未检出脚注/批注标记；四章含图片或对象标记，原始RTF均留存。

## 使用

在项目根目录的 PowerShell 中运行：

```powershell
python -m pip install -r readerTool/requirements.txt
python readerTool/setup_runtime.py
# 先导出三部重点史书
python readerTool/export_corpus.py --book B01-137 --book B01-138 --book B02-163
# 全库；只跳过来源/DLL/解码版本/输出哈希一致、零失败的既有结果
python readerTool/export_corpus.py --all --resume --workers 4
```

默认源目录为 `E:\汉籍全文检索系统`，可通过 `--root` 或环境变量 `HANJI_ROOT` 指定。默认输出在 `readerTool/.local/exports`，可用 `--output` 更改；输出不得位于原书库内部。`--python32` 可指定其他 x86 Python，`--timeout` 为每本书原生解码进程的超时秒数。下载脚本从 Python 官方 HTTPS 地址获取固定版本3.12.10的win32嵌入包，校验固定SHA256后仅解压到本模块`.local`。

本机重点样本：旧唐书215章、新唐书248章、资治通鉴294章，共757章、8,145,506个Unicode字符；机器解析零失败。这是提取和严格编码验证，不是逐字校勘结论。全库每次运行的实际覆盖范围以本机 `run-summary.json` 为准。

2026-10-22本机全量实测：836部、37,085条源记录，37,083条非空正文，共277,138,706个字符、3,147,234个段落。C13-618的29/31两条源记录标题为空，原RTF仅空白字符，作为metadata_only保留，批次因此以非零退出码提示需要检查。独立审计全部来源AMG与JSONL哈希、篇章次序和段落覆盖均通过；另计私用区字符7,424个、RTF图片/对象16项，须保留缺字和非文字内容的复核边界。

## 输出与核验

- `.local/raw/<book-id>/000020.rtf`：DLL返回的原始字节，另有逐章 `manifest.jsonl`。
- `.local/exports/<book-id>.jsonl`：UTF-8，每行一章，含原文及按行划分的段落。稳定章ID是 `book_id:chapter_index`，index从0开始，不等于史书卷号。
- `.local/exports/<book-id>.report.json`：来源SHA256、DLL SHA256、解码器版本、输出SHA256、篇章/字符数、扩展字符、私用区、对象及错误明细。
- `.local/exports/run-summary.json`：全批次当前进度、成功与失败书目。进程异常、文章解析失败分别计数；零失败才退出0。

每章保留书名、章标题、来源AMG SHA256、原RTF SHA256、DLL SHA256和版本。原AMG导出前后重新哈希核对。先写`.part.jsonl`，完成后才原子替换正式JSONL；不可导入`.part`。未知格式或无法严格解码的章保留 `metadata_only`、`text=null` 与失败原因，原始字节留存，不用 `ignore/replace` 拼出假正文。正文解析成功仍一律为 `decoded_unverified`；人工核对须另记范围及证据。

文本合同及入库命令见 [myHistorySys](../myHistorySys/README.md)。全库可能含缺字私用区、异体字、原版本身的录入错误，后续应建立缺字字形映射和抽样校勘。没有恢复原页码或出版版本页面定位，也不复刻旧FTR索引；新服务根据真实文本重建索引。

## 未知字符与独立阅读视图

2026-10-23全库字符普查：7,424次私用区字符、878种码位、415章。对这些章节重新解码并追踪原RTF字体状态，7,424处全部定位，重解码文字与原导出逐字一致。62处属于7种可核对的旧GB18030映射；6,464处使用ICS7，另外898处仍待核。原库附带的Sk4和Ngulim不是ICS7的替代码表，不可仅凭字体有字形就批量替换。

按字体区分有899个“字体、码位”组合，21个码位同时出现在两类字体中；码位相同不能证明字形相同。字体追踪器依赖已固定的striprtf版本，必须通过整章解码与原导出逐字比对；比对失败时撤销该章全部临时追踪，禁止生成新的阅读映射。

确认的7项采用[Unicode ICU的GB18030映射](https://github.com/unicode-org/icu/blob/5f9f8b205337415f4f5ab423cb3fa8b151de5df5/icu4c/source/data/mappings/gb18030-2022.ucm)，映射文件版本、固定commit和SHA256见`gb18030_legacy_map.json`。每次应用同时检查原码位、原始字节、宋体/SimSun字体状态、章身份及原文SHA256，不应用到ICS私用字体。它是独立的`gb18030-legacy-reading-v1`阅读层，不修改v2原文导出、原数据库正文或历史核验状态。

```powershell
python readerTool/inspect_unknowns.py
python readerTool/trace_unknown_fonts.py
python readerTool/build_character_notes.py
```

双击根目录“查看未知字符核对记录.cmd”，打开离线HTML；不启动数据库或API。也可直接打开`readerTool/.local/unknowns/review.html`。支持按书名、章ID、码位、上下文和处理状态筛选，显示来源AMG/RTF哈希、字位、原字节、字体、原文和已核阅读视图。所有含上下文的记录仅保存在`.local/unknowns`，不随开源代码发布。`font-occurrences.jsonl`是逐处证据，`chapter-notes.json`供查询服务加载。

`GET /chapters/{chapter_id}/characters`可返回`original_text`、独立`reading_text`及逐处notes。原文发生变化时拒绝套用旧字位记录。没有记录时不会猜字；尚未解决的字形仍保留。搜索接口继续搜索原始文本，未把阅读层伪装为已重建的全库搜索索引。

在原库附带字库和已安装字体中未找到匹配的ICS7；[CHANT官方字体页](https://www.chant.org/font)的公开CHANT04也不能按原码位直接覆盖这些ICS7记录。本次没有安装字体或绕过登录。其余字符须取得匹配的原ICS字库/可靠转换表或进行逐处字形校勘。

此外保留了U+001A等控制字符的独立统计（U+001A出现277,472次）。这些原始标记未擅自删除或当成普通汉字替换。

## 测试和依赖

```powershell
python -m unittest discover -s readerTool -p 'test_*.py' -v
# 全量独立审计：重新校验来源AMG及每个JSONL，核对身份、篇章和段落覆盖
python readerTool/audit_exports.py --check-source --check-raw
# 有本机报告及reader的npm依赖时，检查离线核对页筛选逻辑
node readerTool/test_character_review.mjs
```

合成RTF测试覆盖混合GBK尾字节、转义括号、字体表分号、GB18030扩展记录、Unicode备用字符、非法编码、截断分组及二进制隔离，不包含史料正文。RTF转换依赖 [striprtf](https://github.com/joshy/striprtf)，固定版本见requirements；原库动态接口是本机特定版本的实测接口，其他版本须重新验证，不能据此假定兼容。
