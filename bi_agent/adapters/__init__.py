"""bi_agent.adapters — 外部依赖适配层（v0.3.2 落地）

设计契约（import-linter 强制）：
  - 实现各 Protocol 接口（adapters/X/base.py 定义）
  - 不得 import services / api / repositories
  - 可 import models / config / core

子包：
  - llm/          : LLMAdapter Protocol + Anthropic / OpenAI / OpenRouter / 私有部署
  - db/           : BusinessDBAdapter Protocol + Doris (v0.3.2 当前实现) + engine_cache
  - notification/ : NotificationAdapter Protocol + Lark stub（v0.4.x 落 impl）

Go 重写映射：本包 → internal/adapter/{llm,db,notification}/。
"""
