# BI-Agent

AI 驱动的 BI 助手：自然语言 → SQL → 图表。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 填写 API Key 和数据库连接
python3 -m uvicorn bi_agent.main:app --reload --port 8000
# 打开 http://localhost:8000
```

## Docker 部署（运维推荐）

```bash
docker build -t bi-agent .
docker run -d -p 8000:8000 --env-file .env bi-agent
```

## 技术栈（v0.1.1）

- **后端：** Python 3 + FastAPI
- **前端：** React + ECharts（浏览器端 Babel，无构建步骤）
- **LLM：** Claude、GPT-4o、Gemini、DeepSeek、OpenRouter
- **存储：** Apache Doris / MySQL（业务查询）+ SQLite（应用元数据）

## 路线图

| 版本 | 状态 | 内容 |
|------|------|------|
| v0.1.1 | ✅ 当前 | Python 基线版本，结构整理，Docker 化 |
| v0.2.0 | 规划中 | Go 后端重写 + Vite 前端构建（团队主力语言） |

## 版本记录

见 [CHANGELOG.md](./CHANGELOG.md)
