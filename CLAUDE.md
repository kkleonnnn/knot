# BI-Agent — Claude Code 项目指令

## 概述

AI 驱动的 BI 助手：自然语言 → SQL → 图表。
- v0.1.1（当前）：Python 3 / FastAPI + React（浏览器端 Babel）
- v0.2.0（规划）：Go 后端重写 + React + Vite 前端构建

## 启动

```bash
# 本地开发
pip install -r requirements.txt
python3 -m uvicorn bi_agent.main:app --reload --port 8000

# Docker 部署
docker build -t bi-agent . && docker run -d -p 8000:8000 --env-file .env bi-agent
```

## 关键路径

| 文件 | 职责 |
|------|------|
| `bi_agent/main.py` | App 工厂，sys.path 设置必须最先执行，注册所有路由 |
| `bi_agent/dependencies.py` | JWT 常量、create_token、get_current_user、require_admin |
| `bi_agent/schemas.py` | 所有 Pydantic 请求模型（9 个） |
| `bi_agent/engine_cache.py` | 用户 DB 引擎缓存（TTL 1h）、_upload_engine |
| `bi_agent/routers/` | 8 个业务域路由文件 |
| `bi_agent/core/` | 核心模块（config, persistence, llm_client, sql_agent, multi_agent 等） |
| `bi_agent/static/` | 前端 SPA（React + ECharts + babel.min.js 3MB） |
| `bi_agent/data/` | SQLite 数据库（gitignore，运行时自动创建） |

## 导入约定

`main.py` 最先执行 `sys.path.insert(0, .../core)`，使 core/ 内模块可用扁平导入
（`import config`、`import persistence` 等）。
`routers/` 通过相对导入拿 `dependencies` 和 `engine_cache`，不需要重复 sys.path 操作。

## 数据库

- `bi_agent/data/bi_agent.db` — 用户 / 会话 / 消息 / 知识库（persistence.py）
- `bi_agent/data/uploads.db` — 用户上传的 CSV / Excel 数据
- Apache Doris / MySQL — 业务查询目标（通过 .env 配置）

## 版本管理

- 版本记录：`CHANGELOG.md`（Keep a Changelog 格式）
- 标签格式：`vMAJOR.MINOR.PATCH.YYYYMMDDHHmm`（如 `v0.1.1.202604252359`）
- 分支策略：`main`（保护，仅打 tag）/ `develop`（集成）/ `feat|fix|chore|hotfix/*`

## 已知技术债

| 优先级 | 问题 | 目标分支 |
|--------|------|---------|
| 高 | 前端 babel.min.js 3MB 首屏慢 | feat/frontend-vite |
| 高 | async 路由中调用 sync SQLAlchemy，高并发阻塞 | feat/async-db |
| 中 | 无结构化日志（全部 print） | chore/structured-logging |
| 低 | uploads.db 与 bi_agent.db 可合并 | — |

## v0.2.0 Go 重写技术栈（分支 feat/go-rewrite）

- HTTP：`gin-gonic/gin` 或 `gofiber/fiber`
- ORM：`gorm.io/gorm`
- LLM：`anthropic/anthropic-sdk-go` + `sashabaranov/go-openai`
- JWT：`golang-jwt/jwt`
- 前端：React + Vite（保留 ECharts 逻辑，加构建步骤）
