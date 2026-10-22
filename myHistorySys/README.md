# myHistorySys：独立原文库与查询服务

接收 `readerTool` 导出的 JSONL，保留原文、来源文件 hash、解码器版本及核验状态，导入 PostgreSQL 后通过 Python API 阅读和检索。查询时不启动汉籍窗口，也不依赖旧 DLL。

2026-10-22本机全量入库与逐章一致性审计：836书库、37085章记录、37083章正文、3147234段、277138706个Unicode字符。JSONL到PostgreSQL的全部章节原文MD5、来源AMG SHA256、身份、标题、decoder、核验状态及每章段数比较，差异为0。C13-618第29、31记录在源库中无标题且正文仅空白，保留为metadata_only，正文为null，未编造标题或内容；API另给display_title显示“原记录无标题”。

这表示文本搬运一致，不表示全部古籍已人工校勘或原书图文版式已复原。源文中的私用区字符、嵌入图像及对象仍须在readerTool报告基础上单独复核，不能用数据库审计通过替代缺字和图文校勘。

## 本机启动

在本目录运行（Windows PowerShell）：

```powershell
# 首次部署；已经初始化的本机环境跳过这三步
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe init_local.py

# 表结构可重复应用；URL从.local/database.url自动读取
.venv/Scripts/python.exe -m historysys.importer --migrate
.venv/Scripts/python.exe -m historysys.importer ../readerTool/.local/exports/B01-137.jsonl
# 批量：只读取已完成.jsonl，排除.part.jsonl，按成功导入hash跳过未变化文件
.venv/Scripts/python.exe import_folder.py ../readerTool/.local/exports
# 首次全库导入私有cluster可暂缓两个GIN索引，COPY写入后一次重建（失败/中断也会finally重建）
.venv/Scripts/python.exe import_folder.py ../readerTool/.local/exports --bulk-index-build
.venv/Scripts/python.exe launch_service.py
# 如需前台观察日志可改用start_service.py；不要与已启动的后台API争用端口
```

服务仅监听 `http://127.0.0.1:18866`，交互接口说明 `/docs`，实际数据库健康检查 `/health`。数据库默认端口55439，仅监听127.0.0.1。`init_local.py`不会安装系统服务，不修改既有数据库或登录账号。只在全新 `.local/postgres-data` 下初始化，已有目录会拒绝覆盖。安装目录的 PostgreSQL bin 必须在PATH中。

`launch_service.py`会核对本目录私有cluster的数据路径，已运行则复用，未运行用pg_ctl后台启动；确认真实数据库健康后后台启动API并打开`/docs`。Windows子进程使用CREATE_NO_WINDOW，日志位于`.local/postgres.log`及`.local/api.log`。端口被别的程序占用或已启动API不健康时停止并提示，不结束未知进程。

本机验证环境为 PostgreSQL16.4，实际连接库 `springhistory_unicode`；同一新建cluster中，前两次locale验证所建的 `springhistory` / `springhistory_text` 为空库，保留未删除。Windows `LC_CTYPE=C` 连同仅指定ICU的尝试，实际 `show_trgm` 均不能切出中文；改用 `Chinese_China.936` 后验证通过。初始化脚本已采用这一locale（非Windows用C.UTF-8），迁移会检查中文trigram是否可用。

`.local/database.url`含随机密码，只保存在本机并被忽略；不要上传或展示。生产部署应另设导入者/只读账号，现阶段是私有本机原型，HTTP没有写入/导入接口，也没有CORS开放。数据目录含古籍正文，不随开源代码发布。临时数据库无需以管理员或Windows系统服务方式运行。

数据库停止后重新启动：

```powershell
pg_ctl -D .local/postgres-data -l .local/postgres.log -w start
# 停止前先关闭查询服务
pg_ctl -D .local/postgres-data -m fast -w stop
```

## 数据合同

每行一章，UTF-8 JSONL，字段：`schema_version=1`、`book_id`、`book_title`、`chapter_id=book_id:chapter_index`、整数`chapter_index`、`chapter_title`、`source_file`、原AMG的`source_sha256`、`decoder`、`verification_status`、`text`、`paragraphs=[{ordinal,text}]`、`metadata={}`。

`decoded_unverified`表示机器解码尚未人工校勘；`verified_sample`仅表示核对了已记录的样本范围，不表示全章逐字校勘；`metadata_only`须为`text=null`且`paragraphs=[]`，不进入正文检索。非空正文须有按原文顺序排列且覆盖全部非空白正文的段落。段落ordinal从0或1开始皆可，但必须非负、唯一、严格递增。原文与段落不被改写；NFKC搜索副本单独保存于normalized列，版本`nfkc-v1`，不进行繁简或标点删改。

`books/chapters/paragraphs/import_runs`位于`history` schema。整份输入在单事务中导入，段落用COPY；任何后续行失败都会回滚前面已写内容。失败导入日志另行保留错误类型，不记录原文或连接密码。重复导入按稳定章ID更新，不产生重复章段；导入审计run会增加。批量恢复核对当前章节持有的导入hash和篇数，不能仅凭历史上曾成功导入就跳过（覆盖X→Y→X有回归测试）。导入过程中输入发生变化会回滚并要求重试。不同导出覆盖相同章ID时以最后成功导入为准，包括核验状态，不自动提升为已核，也不保留正文历史版本。源hash及版本可以追溯当前导入，尚未实现多版本对勘库。

`--bulk-index-build`只允许本模块私有cluster，临时移除固定的两个段落GIN索引；正文仍可扫描读取，正常异常和Ctrl+C都通过finally重建索引。如果进程被强制结束或机器断电，重跑同一批量命令可恢复；也可显式`--migrate`补建索引。维护DDL不受API的15秒查询超时约束，索引重建期间会输出阶段日志。

## API

- `GET /books?limit=50&offset=0`
- `GET /books/B01-137/chapters`
- `GET /chapters/B01-137:18`（章ID须用导出数据实际值，不以卷号猜测index）
- `GET /chapters/{chapter_id}/paragraphs`
- `GET /search?q=五年内不加税赋&book_id=B01-137&limit=20&offset=0`
- `GET /search?q=宣宗&book_id=B01-137`（1/2字以书目范围过滤+LIKE扫描，未声称有短词倒排索引）

默认搜索原文中的连续字面短语，保留标点及空白，不跨段落匹配。`normalized=true`明确切换到NFKC副本，返回命中位置也属于规范化字符串，不可直接当成原文字位。位置按Unicode codepoint、从0开始；每条结果带书名、章标题、段落号、原文、来源hash、解码器及核验状态。`has_more`供分页，不运行全库精确count。查询词限制200字符、单页100条；数据库语句超时15秒。所有用户值参数化，`%`、`_`及反斜杠均按字面匹配。

3字以上中文/拉丁连续短语可利用GIN pg_trgm过滤，仍精确LIKE复核；带大量标点或无可提取trigram的输入可能扫描，不能保证每次查询都走索引。没有将PostgreSQL默认英文tsvector冒充中文分词。后续可添加bigram倒排、异体字索引、近邻、同句和跨段检索。

## 测试与来源

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
# 仅在专门的测试/本机私有库启用真实PG集成（会新增审计run并清理TEST_SYNTHETIC测试章）
$env:HISTORY_TEST_DB='1'
# 必须是单独的测试库，不指向正式原文库；密码放环境变量或安全本机配置，勿入仓库
$env:HISTORY_TEST_DATABASE_URL='postgresql://test_user:CHANGE_ME@127.0.0.1:55439/springhistory_tests'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

合成测试正文显式标记为SYNTHETIC，不是史料还原结果；测试结束删除测试书章，保留导入审计。真实史料验收另见本机`.local/integration-<book-id>.json`（如已生成）。可运行`.venv/Scripts/python.exe verify_query.py B01-137 五年内不加税赋`重新核对真实HTTP查询结果、原文一致性及来源hash；这一检查不提升正文校勘状态。依赖版本约束见requirements，当前环境安装清单保存在`.local/installed-packages.txt`，不包含古籍。

全量入库后运行`.venv/Scripts/python.exe audit_database.py ../readerTool/.local/exports`，可逐章比较JSONL与PostgreSQL的原文UTF8 MD5、标题、身份、原AMG SHA256、decoder、核验状态和每章段落数。报告写入`.local/database-audit-latest.json`。这验证的是搬运保真，不表示史料逐字校勘。

实现核对了官方文档：[pg_trgm索引与LIKE限制](https://www.postgresql.org/docs/current/pgtrgm.html)、[psycopg3参数化](https://www.psycopg.org/psycopg3/docs/basic/params.html)、[事务提交及回滚](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)。
