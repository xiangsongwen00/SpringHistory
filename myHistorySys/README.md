# myHistorySys：独立原文库与查询服务

接收 `readerTool` 导出的 JSONL，保留原文、来源文件 hash、解码器版本及核验状态，导入 PostgreSQL 后通过 Python API 阅读和检索。查询时不启动汉籍窗口，也不依赖旧 DLL。

2026-10-22本机全量入库与逐章一致性审计：836书库、37085章记录、37083章正文、3147234段、277138706个Unicode字符。JSONL到PostgreSQL的全部章节原文MD5、来源AMG SHA256、身份、标题、decoder、核验状态及每章段数比较，差异为0。C13-618第29、31记录在源库中无标题且正文仅空白，保留为metadata_only，正文为null，未编造标题或内容；API另给display_title显示“原记录无标题”。

这表示文本搬运一致，不表示全部古籍已人工校勘或原书图文版式已复原。源文中的私用区字符、嵌入图像及对象仍须在readerTool报告基础上单独复核，不能用数据库审计通过替代缺字和图文校勘。

## 本机启动

在本目录运行（Windows PowerShell）：

```powershell
# 首次安装Python依赖；已配置的本机跳过
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
# 先在既有PostgreSQL中准备专用数据库，并设置HISTORY_DATABASE_URL
# 本机连接配置保存在.local/database.url，不在终端回显密码

# 表结构可重复应用；URL从.local/database.url自动读取
.venv/Scripts/python.exe -m historysys.importer --migrate
.venv/Scripts/python.exe -m historysys.importer ../readerTool/.local/exports/B01-137.jsonl
# 批量：只读取已完成.jsonl，排除.part.jsonl，按成功导入hash跳过未变化文件
.venv/Scripts/python.exe import_folder.py ../readerTool/.local/exports
# 显式批量导入时可暂缓history的两个GIN索引，完成/异常时重建
.venv/Scripts/python.exe import_folder.py ../readerTool/.local/exports --bulk-index-build
.venv/Scripts/python.exe launch_service.py
# 如需前台观察日志可改用start_service.py；不要与已启动的后台API争用端口
```

API仅监听 `http://127.0.0.1:18866`，交互接口说明 `/docs`，实际数据库健康检查 `/health`。本机数据库使用用户已有的`postgresql-x64-16` Windows服务：`127.0.0.1:5432`，数据库`springhistory_unicode`，schema为`history`。迁移使用用户提供并验证的postgres账号，不另建数据库账号；连接凭据仅留本机忽略目录。

`launch_service.py`先只读检查配置的数据库及history表，随后按用户主动启动操作打开API和`/docs`。它不会创建、启动或停止任何PostgreSQL实例，也不会在启动时建表或重建索引。数据库未运行时明确报错，不自动回退到55439。Windows API子进程使用CREATE_NO_WINDOW，日志位于`.local/api.log`；`--no-browser`可禁止打开浏览器。端口被其他程序占用或API不健康时提示，不结束未知进程。

本机验证环境为PostgreSQL16.4，数据库采用支持中文字符分类的UTF8/Chinese_China.936 locale。Windows LC_CTYPE=C下pg_trgm无法切出中文，本项目迁移检查会验证show_trgm。应用连接会将temp_tablespaces置空，仅影响本次会话，使用数据库默认临时存储，避免继承失效的其他临时表空间路径；不修改实例全局参数。

`.local/database.url`含用户授权的数据库连接凭据，只保存在本机并被忽略；不要上传或展示。HTTP没有写入/导入接口，也没有CORS开放。迁移备份、导出数据和数据库文件均不随开源代码发布。

数据库启停由用户管理Windows服务。本项目不代管它的生命周期。旧55439实例已停止，其`.local/postgres-data`和逻辑迁移dump保留为备份，不自动启动。迁移前的`database.url`另存为`.local/database-55439-before-migration.url`。

历史工具`init_local.py`现在必须显式传入`--create-private-cluster`才允许另建实例；使用现有5432服务时不要运行它。

## 数据合同

每行一章，UTF-8 JSONL，字段：`schema_version=1`、`book_id`、`book_title`、`chapter_id=book_id:chapter_index`、整数`chapter_index`、`chapter_title`、`source_file`、原AMG的`source_sha256`、`decoder`、`verification_status`、`text`、`paragraphs=[{ordinal,text}]`、`metadata={}`。

`decoded_unverified`表示机器解码尚未人工校勘；`verified_sample`仅表示核对了已记录的样本范围，不表示全章逐字校勘；`metadata_only`须为`text=null`且`paragraphs=[]`，不进入正文检索。非空正文须有按原文顺序排列且覆盖全部非空白正文的段落。段落ordinal从0或1开始皆可，但必须非负、唯一、严格递增。原文与段落不被改写；NFKC搜索副本单独保存于normalized列，版本`nfkc-v1`，不进行繁简或标点删改。

`books/chapters/paragraphs/import_runs`位于`history` schema。整份输入在单事务中导入，段落用COPY；任何后续行失败都会回滚前面已写内容。失败导入日志另行保留错误类型，不记录原文或连接密码。重复导入按稳定章ID更新，不产生重复章段；导入审计run会增加。批量恢复核对当前章节持有的导入hash和篇数，不能仅凭历史上曾成功导入就跳过（覆盖X→Y→X有回归测试）。导入过程中输入发生变化会回滚并要求重试。不同导出覆盖相同章ID时以最后成功导入为准，包括核验状态，不自动提升为已核，也不保留正文历史版本。源hash及版本可以追溯当前导入，尚未实现多版本对勘库。

`--bulk-index-build`在显式指定的连接库中临时移除history.paragraphs的两个固定GIN索引；正文仍可扫描读取，正常异常和Ctrl+C都通过finally重建索引。它不启动数据库进程。如果进程被强制结束或机器断电，重跑同一批量命令可恢复；也可显式`--migrate`补建索引。维护DDL不受API的15秒查询超时约束，索引重建期间会输出阶段日志。

## API

- `GET /books?limit=50&offset=0`
- `GET /books/B01-137/chapters`
- `GET /chapters/B01-137:18`（章ID须用导出数据实际值，不以卷号猜测index）
- `GET /chapters/{chapter_id}/paragraphs`
- `GET /chapters/{chapter_id}/characters`（字符核对记录、保留原文的独立阅读视图）
- `GET /search?q=五年内不加税赋&book_id=B01-137&limit=20&offset=0`
- `GET /search?q=宣宗&book_id=B01-137`（1/2字以书目范围过滤+LIKE扫描，未声称有短词倒排索引）

默认搜索原文中的连续字面短语，保留标点及空白，不跨段落匹配。`normalized=true`明确切换到NFKC副本，返回命中位置也属于规范化字符串，不可直接当成原文字位。位置按Unicode codepoint、从0开始；每条结果带书名、章标题、段落号、原文、来源hash、解码器及核验状态。`has_more`供分页，不运行全库精确count。查询词限制200字符、单页100条；数据库语句超时15秒。所有用户值参数化，`%`、`_`及反斜杠均按字面匹配。

3字以上中文/拉丁连续短语可利用GIN pg_trgm过滤，仍精确LIKE复核；带大量标点或无可提取trigram的输入可能扫描，不能保证每次查询都走索引。没有将PostgreSQL默认英文tsvector冒充中文分词。后续可添加bigram倒排、异体字索引、近邻、同句和跨段检索。

字符核对接口读取`readerTool/.local/unknowns/chapter-notes.json`，只在源章身份、解码版本和正文SHA256匹配时应用已核编码映射。返回`original_text`与`reading_text`，两者分开，数据库不改写，`verification_status`不升级。报告缺失时明确提示，源文变化或记录错位返回409，避免静默套用过期校改。生成方式见[readerTool说明](../readerTool/README.md)。

## 还原证据与图文资源入库

在本目录运行`.venv/Scripts/python.exe restore_corpus.py --write`，向**当前已配置的数据库**显式应用`002_restoration.sql`并导入，不启动数据库或API。不加`--write`仅检查。脚本验证全部JSONL哈希、字符报告对应的导出版本、全部数据库章节正文SHA256和来源；逐段比较原文、NFKC副本及ordinal，随后在单事务内替换证据表。检查期间对章节/段落表持SHARE锁，允许查询，阻止并发导入；失败回滚证据表写入。

- `history.character_notes`：逐章、逐处的字体、原字节、字位和映射依据，以及独立reading_text。保留全部未解决码位；不改`chapters`、`paragraphs`正文和历史核验状态。
- `history.chapter_assets`：四章内图片/对象的原RTF分组字节、原始RTF哈希、字节范围和可提取payload。对象与fallback可重复表达同一图像，不将资源条数当作图片张数。
- `.local/restoration-audit-latest.json`：本机实际验证及提交结果，含目标数据库名、端口、控制字符统计，不包含密码，不提交Git。

导入后`GET /chapters/{chapter_id}/characters`优先从数据库取证据，并重新验证章身份、来源及正文哈希；尚未导入的旧部署仍可使用本机JSON报告。数据库存储的reading_text是可再生成副本，接口仍按当前映射规则重新构建。普通`/search`继续检索原始文本，尚未对reading_text另建检索索引。

新增只读接口：

- `GET /restoration`：缺字证据、资源统计及过期记录数。
- `GET /chapters/{chapter_id}/assets`：资源清单和来源哈希，位置信息以原RTF字节为准。
- `GET /chapters/{chapter_id}/assets/{ordinal}/download?part=raw`：下载原始分组；`part=payload`下载可明确提取的图片数据。均以二进制附件返回，下载前核对来源和资源SHA256；不执行OLE，也不把未经解析的对象嵌入网页。

上述保存提高了独立库的可追溯性，不等于恢复ICS7缺字字形、解读图中文字或重建原版排版。

2026-10-23本机已在现有5432的`springhistory_unicode`实测提交：37,085章及3,147,234段内容/顺序/规范化副本比对通过；415章的7,424处字符证据入库（62处已核编码映射，7,362处待核）。四章16项资源完整分组入库，其中6项JPEG和8项WMF可提取payload，2项OLE对象保留原始分组。新增两表实际总占用约19MiB，未重复存入全库RTF。

`.venv/Scripts/python.exe verify_restoration.py`使用进程内TestClient和真实数据库，只读验证415章字符接口、16项资源、30次资源下载哈希及三部重点史书查询；不会启动HTTP监听器。实测已在禁止读取本机字符JSON报告的条件下通过，证明这些证据可独立从数据库获取。结果见`.local/restoration-api-check.json`。

## 测试与来源

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
# 仅在专门的测试/本机私有库启用真实PG集成（会新增审计run并清理TEST_SYNTHETIC测试章）
$env:HISTORY_TEST_DB='1'
# 必须是单独的测试库，不指向正式原文库；密码放环境变量或安全本机配置，勿入仓库
$env:HISTORY_TEST_DATABASE_URL='postgresql://test_user:CHANGE_ME@127.0.0.1:5432/springhistory_tests'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

合成测试正文显式标记为SYNTHETIC，不是史料还原结果；测试结束删除测试书章，保留导入审计。真实史料验收另见本机`.local/integration-<book-id>.json`（如已生成）。可运行`.venv/Scripts/python.exe verify_query.py B01-137 五年内不加税赋`重新核对真实HTTP查询结果、原文一致性及来源hash；这一检查不提升正文校勘状态。依赖版本约束见requirements，当前环境安装清单保存在`.local/installed-packages.txt`，不包含古籍。

全量入库后运行`.venv/Scripts/python.exe audit_database.py ../readerTool/.local/exports`，可逐章比较JSONL与PostgreSQL的原文UTF8 MD5、标题、身份、原AMG SHA256、decoder、核验状态和每章段落数。报告写入`.local/database-audit-latest.json`。这验证的是搬运保真，不表示史料逐字校勘。

实现核对了官方文档：[pg_trgm索引与LIKE限制](https://www.postgresql.org/docs/current/pgtrgm.html)、[psycopg3参数化](https://www.psycopg.org/psycopg3/docs/basic/params.html)、[事务提交及回滚](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)。
