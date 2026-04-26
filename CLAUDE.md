# BI-Agent — Claude Code 项目指令

## 概述

AI 驱动的 BI 助手：自然语言 → SQL → 图表。
- v0.1.1：Python 3 / FastAPI + React（浏览器端 Babel）
- v0.2.0（当前）：FastAPI + React/Vite 构建版前端
- v0.x.x（规划）：Go 后端重写

## 协作规则

1. 不确定就问，别猜
2. 没要求就不写
3. 只改被要求的部分
4. 给验收标准，别给步骤

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
| `bi_agent/routers/` | 业务域路由文件（auth / admin / conversations / database / few_shots / knowledge / prompts / query / templates / uploads / user） |
| `bi_agent/core/` | 核心模块（config, persistence, llm_client, sql_agent, multi_agent 等） |
| `bi_agent/static/` | Vite 构建产物（`frontend/` 源码 → `npm run build` 输出至此） |
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

格式：`vMAJOR.MINOR.PATCH.YYYYMMDDHHmm`

- **MAJOR**：`0` = 内测；`1` = 团队公测（由用户决定何时跨过）
- **MINOR**：阶段性大节点（重大重构 / 用户认为"这一阶段已迭代完"）
- **PATCH**：每完成一轮需求迭代 +1
- **时间戳**：每次实际打 tag 的精确时间；同一 PATCH 周期内的小修补只更新时间戳，不动 PATCH

示例：

- 起点：`v0.2.0.xxx`
- 完成本轮 5 点（4/26 16:00）→ `v0.2.1.202604261600`
- 当晚 18:00 修补本轮遗留 → `v0.2.1.202604261800`（PATCH 不动）
- 下一轮新需求完成 → `v0.2.2.xxx`
- 后端 Go 重写或阶段性收尾 → `v0.3.0.xxx`

记录文件：`CHANGELOG.md`（Keep a Changelog 格式）

分支策略：`main`（保护，仅打 tag）/ `develop`（集成）/ `feat|fix|chore|hotfix/*`

## 已知技术债

| 优先级 | 问题 | 目标分支 |
|--------|------|---------|
| 高 | async 路由中调用 sync SQLAlchemy，高并发阻塞 | feat/async-db |
| 中 | 无结构化日志（全部 print） | chore/structured-logging |
| 低 | uploads.db 与 bi_agent.db 可合并 | — |
| 低 | `bi_agent/routers/user.py` 的 `/api/user/config` `/api/user/agent-models` 已无前端调用，留作向后兼容；下个 MINOR 可一并删 | chore/cleanup |

## v0.2.0 Go 重写技术栈（分支 feat/go-rewrite）

- HTTP：`gin-gonic/gin` 或 `gofiber/fiber`
- ORM：`gorm.io/gorm`
- LLM：`anthropic/anthropic-sdk-go` + `sashabaranov/go-openai`
- JWT：`golang-jwt/jwt`
- 前端：React + Vite（保留 ECharts 逻辑，加构建步骤）
