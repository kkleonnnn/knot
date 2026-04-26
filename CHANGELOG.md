# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
