"""tests/adapters/test_async_llm_protocol.py — AsyncLLMAdapter Protocol 守护。

v0.4.0 占位 Protocol；v0.4.4 落 impl（守护测试方向反转：现有 3 adapter 必须满足）。
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


def test_existing_sync_adapters_satisfy_async_protocol_v044():
    """v0.4.4 反转 v0.4.0 占位测试方向（R-31 守护）：
    现有 3 个 adapter 都已实现 acomplete impl，必须满足 AsyncLLMAdapter Protocol。

    v0.4.0 时此测试期望 not isinstance（占位无 impl）；v0.4.4 落 impl 后期望 isinstance。
    """
    from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
    from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
    from bi_agent.adapters.llm.openrouter import OpenRouterAdapter

    for cls in (AnthropicAdapter, OpenAICompatAdapter, OpenRouterAdapter):
        assert isinstance(cls(), AsyncLLMAdapter), (
            f"R-31 守护：{cls.__name__} 应实现 acomplete impl（v0.4.4 落地）"
        )
