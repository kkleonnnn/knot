# BI-Agent

公司内部用的 AI 取数助手：自然语言 → SQL → 图表 + 洞察。

## 角色

- **admin**：配置数据源、API key、3-agent 模型；维护 few-shot / prompt / 知识库
- **analyst**（运营 / 执行）：聊天提问，自动生成 SQL、图表、洞察

## 3-Agent 流式管线

```
Clarifier → SQL Planner → Presenter
（理解）   （ReAct 生成）  （洞察 + 内联异常检查 + 追问建议）
```

- 支持多轮上下文（代词「这些用户」「上述」会自动回指上一题口径）
- SQL 只读 guardrail：sqlglot AST 解析 + DB 端 SHOW GRANTS 探测
- 结构化日志：每个请求带 request_id，grep 即可串起完整 agent 链

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 填 JWT_SECRET、默认数据源
python3 -m uvicorn bi_agent.main:app --reload --port 8000
# http://localhost:8000
```

首次启动后用 admin 账号登录 →「API & 模型」面板填 OpenRouter Key + 给 3 个 agent 选模型。

## Docker

```bash
docker build -t bi-agent .
docker run -d -p 8000:8000 --env-file .env bi-agent
```

## 技术栈（v0.2.2）

- **后端**：Python 3 + FastAPI + SQLAlchemy + SQLite + loguru
- **前端**：React 19 + Vite 8（构建产物输出至 `bi_agent/static/`）
- **LLM**：OpenRouter 统一路由（Anthropic / OpenAI / Google / DeepSeek / Qwen / 智谱 / MiniMax）
- **业务库**：Apache Doris / MySQL（多源按 `host:port:user` 分组合并）
- **RAG**：BM25 + embedding cosine
- **SQL 安全**：sqlglot AST 校验 + DB grants 探测
- **测试**：pytest + yaml 驱动的 eval 集

## 项目结构

详见 [CLAUDE.md](./CLAUDE.md)（包含路径职责、协作规则、版本约定、技术债清单）。

## 版本记录

见 [CHANGELOG.md](./CHANGELOG.md)。

格式 `vMAJOR.MINOR.PATCH.YYYYMMDDHHmm`：MAJOR 0=内测 / 1=团队公测；MINOR=阶段大节点；PATCH=每轮迭代 +1。
