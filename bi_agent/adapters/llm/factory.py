"""factory — 按 provider 名路由到具体 LLMAdapter（v0.3.2 R-7 严格化）。

调用方契约：
    from bi_agent.adapters.llm.factory import get_adapter
    adapter = get_adapter("anthropic")
    resp = adapter.complete(LLMRequest(...))

行为：
  - 已知 provider → 对应 adapter
  - 已知走 OpenAI-compat 协议的 provider（gemini/deepseek/qwen 等）→ OpenAICompatAdapter
  - **未知 provider → 抛 ProviderNotImplementedError**（v0.3.2 前会 silently 兜底，
    R-7 改为显式失败，避免 typo 静默走错通道）
"""
from __future__ import annotations

from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
from bi_agent.adapters.llm.base import LLMAdapter
from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
from bi_agent.adapters.llm.openrouter import OpenRouterAdapter
from bi_agent.models.errors import ProviderNotImplementedError

# 走 OpenAI-compatible HTTP 协议的 provider（包括私有部署的 vllm/ollama）
_OPENAI_COMPAT_PROVIDERS = frozenset({
    "openai", "gemini", "google",
    "deepseek", "qwen", "zhipu", "glm", "minimax",
    "ollama", "vllm",
})

_KNOWN_PROVIDERS = _OPENAI_COMPAT_PROVIDERS | {"anthropic", "openrouter"}


def get_adapter(provider: str) -> LLMAdapter:
    """provider 一律小写匹配；未知 provider 显式抛 ProviderNotImplementedError。"""
    p = (provider or "").lower().strip()
    if p == "anthropic":
        return AnthropicAdapter()
    if p == "openrouter":
        return OpenRouterAdapter()
    if p in _OPENAI_COMPAT_PROVIDERS:
        return OpenAICompatAdapter(provider_label=p)
    raise ProviderNotImplementedError(provider, supported=sorted(_KNOWN_PROVIDERS))
