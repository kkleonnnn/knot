"""bi_agent.services — 业务编排层（v0.3.1 落地）

设计契约（import-linter 强制）：
  - 编排业务流（routers 调用 services；services 调用 repositories / adapters）
  - 不得 import api/routers
  - 可 import models / config / core / repositories / adapters

平铺设计：
  - knot/         : KNOT 核心数据分析业务（产品命名空间，Go 重写时单独划走）
  - auth_service  : 用户认证 + 密码哈希
  - catalog       : 业务目录加载（fallback chain：DB → real → example）
  - few_shots_service : few-shot 示例装配（# FIXME-v0.3.1.next）
  - prompt_service: 3-Agent system prompt 装配
  - rag_service   : 文档 RAG（embedding / cosine 检索）
  - rag_retriever : BM25 retriever（schema 过滤打分用）
  - schema_filter : Schema 精准过滤（BM25 + 业务词典 + 主题加分）
  - llm_client    : 多 provider LLM 路由（# FIXME-v0.3.2: 拆到 adapters/llm/）
"""
