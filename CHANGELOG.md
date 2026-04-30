# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — OHX 真实 schema 接入（4 任务批次）
- **`bi_agent/core/ohx_catalog.py`**：18 张 OHX 表（ohx_dwd × 8 + ohx_ads × 10）目录 + LEXICON 业务词典 + BUSINESS_RULES 规则常量
  - 时区/业务日 14:00 切日 / 真实用户范围 / 默认 USDT / 表分层（聚合 vs 明细 vs 余额）一站式锚定
- **schema_filter v2**：从单纯 BM25 升级为「BM25 + 词典命中加分（+12/+8/+5）+ 主题重合（+3）+ 高优先级强制纳入」，`SCHEMA_FILTER_MAX_TABLES` 25，单次 prompt 上限 12 表
  - 修复回归：「昨天充值 Top 10 用户」类问题不再把 `dwd_user_deposit` 过滤掉
- **eval cases 扩到 31 条**（16 → 31）：分组覆盖 运营日报指标 / 趋势 / 周月报 / 用户名细 / 活动场景（业务日 14:00 + 真实用户范围）/ 邀请代理 / 平台余额 / 套利·折扣购·金鹰宝·结构化 / 做市账号 / 价格 / 安全回归 / 多轮代词
- **few_shots.yaml 重写为 30 条 OHX 真实示例**：替换原通用 orders/users 例子；每条都符合「业务日窗口 + 真实用户 + USDT 默认」三要素
- **`tests/eval/conftest.py`**：fake_schema 改用 OHX 18 表 markdown，与 prompt/词典/few-shot 完全对齐

### Changed — 3 Agent prompt 注入 OHX 业务规则
- Clarifier / SQL Planner / Presenter 三处 system prompt 通过 `{business_rules}` 占位符引入 `ohx_catalog.BUSINESS_RULES`
- Clarifier 加业务规则消歧段：业务日定义 / 测试号排除 / USDT 默认 / 周月报关键词保留
- SQL Planner 规则增加"严格遵守上方业务规则"显式约束

### Verified
- `pytest tests/eval -v`：1 passed / 31 skipped（结构 check 通过；live LLM 待跑）
- schema_filter smoke：「昨天充值 Top 10 用户」选表包含 `dwd_user_deposit` ✅
- multi_agent / sql_agent 模块导入 OHX_RULES 正常

## [0.2.3.202604301140] - 2026-04-30 v0.2.3 回答质量与命中率

### Added
- **`bi_agent/core/date_context.py`**：统一日期口径上下文
  - `today_iso()` / `date_context_block()`，时区显式 `Asia/Shanghai`（fallback `date.today()`）
  - 枚举 今天 / 昨天 / 前天 / 最近7天 / 最近30天 / 本周 / 上周 / 本月 / 上月 → 绝对日期，避免 LLM 把"昨天"映射到训练截止时间
- **跨连接组 SQL 检测**：`MultiSourceEngine.cross_group_dbs()` 解析 SQL 中所有 `db.tbl` 引用，跨组时 `_MultiConn.execute` 抛出明确 `RuntimeError`（"跨连接组查询不支持：本次路由到组 X，但 SQL 还引用了 Y"），不再让 MySQL 回 "Access denied" 误导 LLM 报权限错
- **多组 schema 顶部说明**：列出"组 → 库归属"映射 + "每条 SQL 只能引用同一组内的库"约束
- **eval cases 扩到 16 条**（5 → 16）：覆盖
  - 日期口径：today / last_7days / this_week / last_month
  - 聚合：avg_order_value / paid_user_count / refund_rate
  - 状态过滤：unpaid_pending_orders
  - 趋势：dau_7d_trend
  - 写操作幻觉回归：用户措辞含"删除"时 SQL 仍只读（`readonly_under_destructive_phrasing`）

### Changed
- **Clarifier / SQL Agent / Presenter / build_system_prompt 四处 prompt** 全部从单行 `今日：YYYY-MM-DD` 升级为 `date_context_block()` 完整枚举块
- **Presenter prompt 加幻觉禁令**：
  - 禁止臆造权限错误（输入无"执行失败/Access denied/permission denied"字样时不准说"没有权限"）
  - 空结果集只能解释为数据为零 / 时间窗口外 / 口径过严，不归因到权限
  - 不引用未在结果中出现的数字与字段
  - 不替用户切换日期口径

### Verified
- `pytest tests/eval -v`：1 passed / 15 skipped（结构 check 通过；live LLM 因无 key 跳过）
- SQL guardrail 11 条 smoke 全 pass（SELECT/SHOW pass；DROP/DELETE/UPDATE/INSERT/TRUNCATE/GRANT/CREATE/stacked 全拒）
- MultiSourceEngine 跨组检测 5 条单测全 pass（无 db.tbl / 单组 / 同组多库 / 跨组 / 未知 db）
- TestClient 启动冒烟：`/healthz` 200，`/api/auth/me` 401



### Added
- **SQL 只读 guardrail**（双层）
  - Layer 1: sqlglot AST 解析替换原正则黑名单；单语句 + 只读根节点 + AST 内零写/DDL/Command 节点；stacked query 拒绝。18 条 smoke test 全 pass
  - Layer 2: engine 构建后探测 SHOW GRANTS，writable 默认 warn-only；`STRICT_READONLY_GRANTS=1` 改为强制拒绝
- **结构化日志**（loguru + request_id）
  - `bi_agent/core/logging_setup.py`：stderr 彩色 + 文件 rotate（每天 0 点切，保留 7 天，写到 `data/logs/`）
  - HTTP middleware 给每个请求分配 12 位 request_id；`X-Request-ID` 透传 + 回写
  - clarifier / sql_planner / presenter 链路各打 1 行；grep request_id 即可串起完整 agent 链
- **Eval runner 框架**
  - `tests/eval/cases.yaml`：5 条覆盖 metric/trend/compare/rank/distribution
  - `tests/eval/test_eval.py`：parametrize 跑 generate_sql，断言 must_tables / must_keywords / forbid_keywords
  - 无 `OPENROUTER_API_KEY` 时整组 skip；额外保留结构校验
- **scripts/profile_pyspy.sh**：attach 运行中进程跑 top / 抓 60s 火焰图 / dump 栈

### Changed
- **3-Agent 流式管线**（砍 Validator）：Presenter 内联异常检查，输出 `confidence: high|medium|low` 字段；前端 medium 黄底、low 红底徽标；retry-on-low-confidence 逻辑随 Validator 一起删除
- **并发能力**：startup 把 anyio 默认线程池从 40 提到 64（`ANYIO_TOKENS` 可调），缓解 LLM 同步 SDK 阻塞
- CLAUDE.md 技术债表更新：标注真正的 async LLM 留到下个 MINOR；结构化日志已落地

### Removed
- `validator` agent 全链路代码（multi_agent / query router / schemas / admin&user 路由 / prompts router / 模板 / seed / 前端 Admin&Chat）

### Dependencies
- `sqlglot>=25.0.0`、`loguru>=0.7.2`

### Verified
- `pytest tests/eval -v` 1 passed / 5 skipped（结构 check 通过，LLM live skip 因无 key）
- `_is_safe_sql` 18 条 smoke 用例全 pass：DROP/INSERT/UPDATE/DELETE/TRUNCATE/GRANT/CALL/CREATE/SET/USE/stacked query 全拒，SELECT/CTE/SHOW/DESCRIBE 全过
- TestClient GET /healthz 200, /api/auth/me 401，request_id 中间件日志正常输出

## [0.2.1.202604270250] - 2026-04-27 查询页瘦身

### Removed
- 聊天侧栏「表结构」tab + `SchemaPanel`/`useDebounce`/`/api/db/schema` 拉取（运营人员不需要直接接触库表，schema 由 sql_planner 在后端使用）
- 输入框「多Agent」开关：默认走 4-Agent 流式管线；非流式 `/query` 分支 + `useAgent` 状态/props 全删

### Changed
- 侧栏简化为单一历史列表（无 tab 切换）
- `AgentThinkingPanel` 仅在有事件时渲染

## [0.2.1.202604270230] - 2026-04-27 v0.2 收尾

### Changed
- CLAUDE.md：技术债表移除「前端 babel.min.js 3MB 首屏慢」（v0.2.0 Vite 构建已闭环）；新增低优条目记录 `bi_agent/routers/user.py` 待清理
- CLAUDE.md：`bi_agent/routers/` 列表对齐当前 11 个 router；`bi_agent/static/` 注释更新为 Vite 产物

### Removed
- 删除前端死代码 `frontend/src/screens/UserConfig.jsx`（v0.2.1 批次2 起 admin 重定向至 `/admin-models`、analyst 无入口，此屏不再被路由命中）；同步移除 App.jsx 的无效 import

### Verified
- `npm run build` 通过；产物 1395 KB / gzip 446 KB，与移除前一致（dead-code，bundle 未变）
- 历史 [Known issues] 全部闭环：clarifier 字段盲区 / schema 跨库截断 / 跨连接多源 / analyst 404 / 未来日期误判 / 多轮代词 6 项均已 Fixed

## [0.2.1.202604270215] - 2026-04-27 批次5（多轮上下文）

### Fixed
- 多轮代词无法关联：history 传给 clarifier 时只有 Q 文本，丢掉 SQL/结果，导致"这些用户"无法回指上一轮口径；现在 history 渲染为 `Q + SQL + 前 2 行结果`
- Clarifier prompt 增加强制代词解析规则：遇到「这些/上述/刚才的/他们/那批」必直接 is_clear=true，禁止以"聚合表无明细/是否存在 xx 表"为由追问（属 sql_planner 责任）；附正确示例

### Verified
- Q1 "2026-04-25 注册用户数" → 8 人（ads_operation_report_daily 聚合）
- Q2 "把这些用户的ID列一下" → clarifier 一次明确 → sql_planner 自动从 ads 切到 ohx_dwd.dwd_user_reg → 返回 8 个 user_id（与 Q1 数值对应）

## [0.2.1.202604270145] - 2026-04-27 批次4（日期感知 + 业务化 prompt seed）

### Fixed
- 未来日期误判：clarifier / validator 因 LLM 训练截止时间把 ≤ 今日的日期判为"未来"，触发无谓重试（42s→11s）。4 个 agent prompt 全部注入 `今日：YYYY-MM-DD`（系统时间为权威）；llm_client.build_system_prompt 同步注入

### Added
- `prompts.get_prompt` 支持 `{__default__}` 占位符 → admin 可在 DB 中写"默认 + 业务追加"而不必抄全文
- `scripts/seed_v021_b3.py` 一次性 seed：6 条 few-shot（metric/trend/compare/rank/distribution/retention 6 类型覆盖）+ 4 个 agent 的业务追加约束（时间口径、字段映射、SQL 风格、洞察文风）

### Verified（端到端 OpenRouter 实测）
- "2026年4月25日注册用户数是多少" → clarifier 一次明确 / sql_planner 1 步 / validator high / presenter 8 人 + 2 条 followup，11.9s, $0.0079

## [0.2.1.202604262315] - 2026-04-26 批次3（遗留收尾）

### Fixed
- analyst 提问 404：登录/登出未清 `cb_conv`，跨账号继承陈旧 conv_id 导致 POST `/api/conversations/{id}/query` 404；登录与登出均清掉 `cb_conv`，并在 `loadConvs` 校验 activeConvId 不在列表时自动重置；首次发问无 conv 时直接用新建返回的 id 发送（不再依赖 setState 异步）
- Clarifier 字段盲区：原来只看表名清单 25 张，把"昨天注册用户数"这种明确问题误判为需澄清；改为把完整 schema（表 / 字段 / 注释）截前 6000 字喂给 clarifier，prompt 提示"字段注释能对应概念时不要追问"
- Schema 截断跨库失衡：`get_schema` 改为按 DB 平均配额抽样，每个库都至少进入 schema，避免后置库（ohx_dwd）一张表都进不来
- 跨连接多源 schema 合并：用户跨 `(host,port,user)` 多组 datasource 时，新增 `MultiSourceEngine` 派发引擎；`get_schema` 按组分别抓取并以 "## 连接组 {key}" 头部串接；`execute_query` 在 `_MultiConn.execute` 时按 SQL 中首个 `db.tbl` 前缀路由到对应组的 engine

### Changed
- `engine_cache._engine_cache` 多组场景缓存 key 改为 `(uid, "multi:"+sorted_keys)`；`SCHEMA_FILTER_MAX_TABLES` 在多组时按组均分配额（最低 4）

## [0.2.1.202604262115] - 2026-04-26 批次2

### Added
- B2 few-shot 可视化：`few_shots` 表 + admin `/api/few-shots` CRUD + xlsx 批量导入；DB 为空时自动回退 `few_shots.yaml`
- B2 Prompt 模板：`prompt_templates` 表 + admin `/api/prompts` CRUD + xlsx 批量导入；4 个 agent（clarifier / sql_planner / validator / presenter）可独立覆盖 system prompt，留空使用内置默认
- B2 模板下载：`/api/templates/{few_shots|prompts|knowledge}` 提供 xlsx / txt 下载
- B3 admin API Key 集中管理：`/api/admin/api-keys`（OpenRouter + Embedding）；存 `app_settings` 表
- B3 admin 4-Agent 模型分配 UI（复用已有 `/api/admin/agent-models`）
- 前端 Admin 新增 Few-shot / Prompt 两个 tab；模型 tab 顶部新增 API Key + 4-Agent 模型分配两块卡片
- `bi_agent/core/prompts.py`：通用 prompt 加载器（DB 优先 / 默认回退 / 安全占位符替换）

### Changed
- API Key 与 4-agent 模型配置归口管理员；用户不再有任何 key 输入入口
- `multi_agent._resolve` / `sql_agent.run_sql_agent` / `llm_client._invoke_*` / `query.py` / `knowledge.py` 改为优先读 `app_settings.openrouter_api_key` / `embedding_api_key`
- `query.py` agent 模型配置从 per-user (`get_user_agent_model_config`) 切换到 admin 级 (`get_agent_model_config`)
- `frontend/src/Shell.jsx` 移除「个人」分区的 API & 模型入口；admin-models 改名为「API & 模型」
- `frontend/src/App.jsx` user-config / settings 路由对 admin 重定向到 admin-models 面板

### Migration（一次性）
- 清空 `users.openrouter_api_key` / `embedding_api_key` / `agent_model_config`（写入 `app_settings._v021b2_user_keys_cleared` 标记防重复）

### Known issues（沿用上一段）
- Clarifier 字段盲区 / Schema 截断跨库失衡 / 跨连接多源 schema 合并 / analyst 提问 404（待下一轮）

## [0.2.1] - 2026-04-26

### Changed
- 角色精简：移除 `viewer`，仅保留 `admin` / `analyst`；analyst 无任何设置入口（齿轮 / `/settings` 兜底重定向）
- 模型库扩充至 8 类厂商：Anthropic / OpenAI / Google / DeepSeek / Qwen / 智谱 GLM / MiniMax（OpenRouter 通道），保留原生直连模型
- `_is_openrouter_model()` 改为按 `provider` 字段判定，统一 `sql_agent` / `multi_agent` / `llm_client` 三处的 OR 路由

### Fixed
- 多数据源 `(host, port, user)` 同组合并 db_database：解决 `engine_cache` 用 `sources[0]` 账号访问其他 source 库的"无权限"问题；缓存 key 从 `uid` 改为 `(uid, group_key)`，避免多组互相覆盖
- 401 死循环：`api.js` 401 处理仅清 `cb_token` 但不清 `cb_user`，导致重载后仍渲染 ChatScreen → 再 401 → 再 reload。补全清理 `cb_user` / `cb_screen` / `cb_conv` / `cb_loading`
- Vite `/assets/*` 静态资源被 SPA catch-all 兜回 index.html 的白屏：补 `/assets` mount + SPA 路由先判 `is_file()`

### Known issues（下一轮）
- Clarifier 仅看表名清单、看不到字段注释，对明确问题（如"昨天注册用户数"）会误判需澄清
- `SCHEMA_FILTER_MAX_TABLES=10` + 多库合并后截断：后置库（如 ohx_dwd）一张表都进不来
- 跨 `(host, port, user)` 多源场景仅 warning + 取第一组（schema 按源分组 + 按表选 engine 待下一轮）
- analyst 角色提问报 `{"detail":"Not Found"}` 404（待定位：可能 conversation 未创建即发送 / analyst 未关联数据源 / 隐性 admin-only 路由）

## [0.1.1] - 2026-04-26

### Added
- Git 初始化，上传 GitHub（私有仓库）
- README.md、CLAUDE.md、CHANGELOG.md
- Dockerfile（运维容器化部署）
- 项目结构重构：main.py 拆分为 8 个 router 模块
- dependencies.py（JWT + auth 依赖）、schemas.py（Pydantic 模型）、engine_cache.py（DB 引擎缓存）

### Architecture (Python 基线版本)
- 35 个 API 端点，8 个 router 模块
- 多 LLM 路由：Claude、GPT-4o、Gemini、DeepSeek、OpenRouter
- ReAct SQL Agent + 4 阶段 orchestration（Clarifier / SQL Planner / Validator / Presenter）
- 文档 RAG（BM25 + embedding cosine similarity）
- React SPA 前端（浏览器端 Babel，无构建步骤）

### Roadmap
- v0.2.0：Go 后端重写 + Vite 前端构建（团队主力语言，解决并发瓶颈）
