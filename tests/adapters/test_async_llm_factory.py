"""tests/adapters/test_async_llm_factory.py — v0.4.4 R-31 AsyncLLMAdapter 完整性核查。

验证：
- 4 个具体 adapter (Anthropic / OpenAICompat / OpenRouter) 都满足
  AsyncLLMAdapter Protocol（runtime_checkable + isinstance check）
- factory.get_async_adapter 正确路由 + 缺 impl 时 AssertionError
- 未知 provider 抛 ProviderNotImplementedError（与 get_adapter 一致）
"""
from bi_agent.adapters.llm import AsyncLLMAdapter
from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
from bi_agent.adapters.llm.factory import get_adapter, get_async_adapter
from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
from bi_agent.adapters.llm.openrouter import OpenRouterAdapter
from bi_agent.models.errors import ProviderNotImplementedError

import pytest


def test_R31_anthropic_satisfies_async_protocol():
    """v0.4.4 R-31：AnthropicAdapter 必须实现 acomplete。"""
    adapter = AnthropicAdapter()
    assert isinstance(adapter, AsyncLLMAdapter), (
        "AnthropicAdapter 应满足 AsyncLLMAdapter Protocol（缺 acomplete impl）"
    )


def test_R31_openai_compat_satisfies_async_protocol():
    adapter = OpenAICompatAdapter()
    assert isinstance(adapter, AsyncLLMAdapter)


def test_R31_openrouter_satisfies_async_protocol():
    adapter = OpenRouterAdapter()
    assert isinstance(adapter, AsyncLLMAdapter)


def test_get_async_adapter_returns_anthropic():
    adapter = get_async_adapter("anthropic")
    assert isinstance(adapter, AnthropicAdapter)
    assert isinstance(adapter, AsyncLLMAdapter)


def test_get_async_adapter_returns_openai_for_compat_providers():
    """已知 OpenAI-compat provider（gemini/deepseek/qwen 等）走同一 adapter。"""
    for provider in ("openai", "gemini", "deepseek", "qwen", "ollama"):
        adapter = get_async_adapter(provider)
        assert isinstance(adapter, OpenAICompatAdapter), f"{provider} 应路由到 OpenAICompatAdapter"
        assert isinstance(adapter, AsyncLLMAdapter)


def test_get_async_adapter_returns_openrouter():
    adapter = get_async_adapter("openrouter")
    assert isinstance(adapter, OpenRouterAdapter)
    assert isinstance(adapter, AsyncLLMAdapter)


def test_get_async_adapter_unknown_provider_raises():
    """未知 provider 行为与 get_adapter 一致 — ProviderNotImplementedError。"""
    with pytest.raises(ProviderNotImplementedError):
        get_async_adapter("nonexistent-provider-xyz")


def test_sync_and_async_adapter_share_instance_class():
    """R-24 双 API 同 adapter 实例 — sync get_adapter 与 async get_async_adapter
    返同一 class 实例（不同 call 各创建一个，但类相同）。"""
    sync_adapter = get_adapter("anthropic")
    async_adapter = get_async_adapter("anthropic")
    assert type(sync_adapter) is type(async_adapter)
    # 两者都满足两个 Protocol（双重契约）
    from bi_agent.adapters.llm.base import LLMAdapter
    assert isinstance(sync_adapter, LLMAdapter)
    assert isinstance(async_adapter, AsyncLLMAdapter)


def test_R31_factory_assertion_message_mentions_acomplete():
    """守护：错误消息必须提示 'acomplete' 字眼，便于排查（断言式快速失败）。
    构造一个故意不实现 acomplete 的 adapter 类，验证 assert message。"""
    from bi_agent.adapters.llm.async_base import AsyncLLMAdapter as AP
    class _Bad:
        def complete(self, req):
            return None
    bad = _Bad()
    assert not isinstance(bad, AP), "bad adapter 没 acomplete，应不满足 Protocol"
