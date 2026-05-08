"""bi_agent.adapters.llm — LLM 适配层（v0.3.2 sync + v0.4.4 async）

调用契约（sync）：
    from bi_agent.adapters.llm import LLMRequest, get_adapter
    adapter = get_adapter("openrouter")
    resp = adapter.complete(LLMRequest(...))

调用契约（async, v0.4.4）：
    from bi_agent.adapters.llm import LLMRequest, get_async_adapter
    adapter = get_async_adapter("openrouter")
    resp = await adapter.acomplete(LLMRequest(...))
"""
from bi_agent.adapters.llm.async_base import AsyncLLMAdapter  # noqa: F401  v0.4.4
from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse, calculate_cost  # noqa: F401
from bi_agent.adapters.llm.factory import get_adapter, get_async_adapter  # noqa: F401
