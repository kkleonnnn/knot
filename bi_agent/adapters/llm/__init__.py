"""bi_agent.adapters.llm — LLM 适配层（v0.3.2）

调用契约：
    from bi_agent.adapters.llm.base import LLMRequest, LLMResponse
    from bi_agent.adapters.llm.factory import get_adapter

    adapter = get_adapter("openrouter")
    resp = adapter.complete(LLMRequest(model_key="...", system="...", messages=[...], api_key="..."))
"""
from bi_agent.adapters.llm.async_base import AsyncLLMAdapter  # noqa: F401  v0.4.4 落 impl
from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse, calculate_cost  # noqa: F401
from bi_agent.adapters.llm.factory import get_adapter  # noqa: F401
