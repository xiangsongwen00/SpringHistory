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

## 测试和依赖

```powershell
python -m unittest discover -s readerTool -p 'test_*.py' -v
# 全量独立审计：重新校验来源AMG及每个JSONL，核对身份、篇章和段落覆盖
python readerTool/audit_exports.py --check-source --check-raw
```

合成RTF测试覆盖混合GBK尾字节、转义括号、字体表分号、GB18030扩展记录、Unicode备用字符、非法编码、截断分组及二进制隔离，不包含史料正文。RTF转换依赖 [striprtf](https://github.com/joshy/striprtf)，固定版本见requirements；原库动态接口是本机特定版本的实测接口，其他版本须重新验证，不能据此假定兼容。
