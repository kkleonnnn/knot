# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
