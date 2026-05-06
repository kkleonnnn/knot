"""factory — 按 provider 名路由到具体 LLMAdapter。

调用方契约（services/llm_client 用）：
    from bi_agent.adapters.llm.factory import get_adapter
    adapter = get_adapter("anthropic")
    resp = adapter.complete(LLMRequest(...))
"""
from __future__ import annotations

from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
from bi_agent.adapters.llm.base import LLMAdapter
from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
from bi_agent.adapters.llm.openrouter import OpenRouterAdapter


def get_adapter(provider: str) -> LLMAdapter:
    """provider 一律小写；未知 provider 默认走 openai_compat（多数私有部署兼容）。"""
    p = (provider or "").lower()
    if p == "anthropic":
        return AnthropicAdapter()
    if p == "openrouter":
        return OpenRouterAdapter()
    # openai / gemini / deepseek / ollama / vllm / qwen / glm / minimax 等
    return OpenAICompatAdapter(provider_label=p or "openai")
