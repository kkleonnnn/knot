"""factory — 按 provider 名路由到具体 LLMAdapter（v0.3.2 R-7 严格化）。

调用方契约：
    from knot.adapters.llm.factory import get_adapter
    adapter = get_adapter("anthropic")
    resp = adapter.complete(LLMRequest(...))

行为：
  - 已知 provider → 对应 adapter
  - 已知走 OpenAI-compat 协议的 provider（gemini/deepseek/qwen 等）→ OpenAICompatAdapter
  - **未知 provider → 抛 ProviderNotImplementedError**（v0.3.2 前会 silently 兜底，
    R-7 改为显式失败，避免 typo 静默走错通道）
"""
from __future__ import annotations

from knot.adapters.llm.anthropic_native import AnthropicAdapter
from knot.adapters.llm.async_base import AsyncLLMAdapter
from knot.adapters.llm.base import LLMAdapter
from knot.adapters.llm.openai_compat import OpenAICompatAdapter
from knot.adapters.llm.openrouter import OpenRouterAdapter
from knot.models.errors import ProviderNotImplementedError

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


def get_async_adapter(provider: str) -> AsyncLLMAdapter:
    """v0.4.4 R-31：返同一 adapter 实例（adapter 同时实现 sync + async 两套）。
    runtime check 验证 acomplete 存在；缺失立即报错而非运行时 AttributeError。

    R-30：未知 provider 抛 ProviderNotImplementedError（与 get_adapter 一致）；
    Protocol 不满足时 AssertionError（开发期错；生产不应触发）。
    """
    adapter = get_adapter(provider)
    assert isinstance(adapter, AsyncLLMAdapter), (
        f"R-31 守护：{provider} adapter 缺 acomplete impl；"
        f"v0.4.4 起所有 LLM adapter 必须实现 async 版本"
    )
    return adapter
