# 来源与第三方声明

SpringHistory 是独立的史料整理与本机阅读项目。

阅读引擎基于 [xiangsongwen00/0-readmd](https://github.com/xiangsongwen00/0-readmd)，导入时的提交为 `ccf4430`；保留了上游源文件作者注释及 `reader/readme.md`。上游 package.json 标注 ISC，部分上游文件另有作者版权注释，这些原有声明均保留，SpringHistory 的 LICENSE 不替换它们。

新增部分包括案例与纪年导航、docs内容加载、本机汉籍适配、启动入口、makeDocs工作规则与工具，以及相应测试。新增代码按本项目 ISC License 提供。

npm/Python依赖继续遵循各自许可，依赖清单与版本记录见 `reader/package-lock.json` 和 `reader/requirements-reader.txt`。

汉籍全文检索系统是用户自行安装的本机程序，本仓库不包含其可执行文件、数据库、帮助文件或授权。使用本机查询功能需自行准备可用安装。运行时日志、桌面截图、本机目录扫描结果与虚拟环境不随仓库发布。

历史资料示例保留书名、卷次、转录来源及待考说明；自动定位成功不等于所有引文已经校勘。

`readerTool` 的RTF转换使用 [striprtf](https://github.com/joshy/striprtf)（BSD-3-Clause），通过依赖安装，不在仓库复制其源代码；可选x86运行时来自Python官方嵌入发行包，下载在忽略的`.local`内，受Python相应许可约束。`myHistorySys`的FastAPI、Uvicorn、psycopg和PostgreSQL各自遵循原许可。调用的本机`Ftrquery.dll`及解码输出不随本仓库发布；SpringHistory的许可证不授予这些本机资料的再分发权。

独立字形阅读层的7项GB18030映射依据[Unicode ICU映射数据](https://github.com/unicode-org/icu/blob/5f9f8b205337415f4f5ab423cb3fa8b151de5df5/icu4c/source/data/mappings/gb18030-2022.ucm)，固定来源与SHA256见`readerTool/gb18030_legacy_map.json`，原数据受[Unicode许可](https://www.unicode.org/license.txt)约束。原库字体、下载的CHANT字体、字形图和含原文上下文的核对记录仅保留在本机忽略目录，不在本仓库再分发。
