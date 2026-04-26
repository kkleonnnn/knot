# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
