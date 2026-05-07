"""tests/adapters/test_async_llm_protocol.py — v0.4.0 AsyncLLMAdapter 占位 Protocol。

v0.4.4 落 impl；本 PATCH 仅锁 shape。
"""
from __future__ import annotations

from bi_agent.adapters.llm import AsyncLLMAdapter
from bi_agent.adapters.llm.base import LLMRequest, LLMResponse


def test_async_protocol_runtime_check_accepts_acomplete_class():
    class _Stub:
        async def acomplete(self, req: LLMRequest) -> LLMResponse:
            return LLMResponse(text="ok")

    assert isinstance(_Stub(), AsyncLLMAdapter)


def test_async_protocol_rejects_class_without_acomplete():
    class _Bad:
        def complete(self, req):  # 同步签名，缺 acomplete
            return LLMResponse(text="")

    assert not isinstance(_Bad(), AsyncLLMAdapter)


def test_existing_sync_adapters_do_not_satisfy_async_protocol():
    """v0.4.0 不强制现有 4 个 adapter 实现 acomplete；
    runtime check 必须返 False，证明 v0.4.4 落 impl 时确实需要补全。"""
    from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
    from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
    from bi_agent.adapters.llm.openrouter import OpenRouterAdapter

    for cls in (AnthropicAdapter, OpenAICompatAdapter, OpenRouterAdapter):
        assert not isinstance(cls(), AsyncLLMAdapter), (
            f"{cls.__name__} 已无意中实现 acomplete；请检查 v0.4.4 计划"
        )
