"""openrouter — OpenRouter 统一路由（v0.2.x 主路径）。

实现细节：OpenRouter 走 OpenAI-compatible 协议，所以本 adapter 复用 openai_compat
逻辑，只把 provider 标签换成 "openrouter"，让错误消息更精确。

把 openrouter 单独建文件而非塞进 openai_compat，是为了 Go 重写时能 1:1 映射到
internal/adapter/llm/openrouter.go（OR 是当前 7 厂商的统一入口，单独一个文件
便于后续加 OR-specific 行为，如 fallback model / route header）。
"""
from __future__ import annotations

from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter


class OpenRouterAdapter:
    """实现 LLMAdapter (sync) + AsyncLLMAdapter (async) — 复用 OpenAICompatAdapter
    内核（v0.4.4 R-31：sync + async 都委托给 inner adapter）。"""

    def __init__(self):
        self._inner = OpenAICompatAdapter(provider_label="openrouter")

    def complete(self, req: LLMRequest) -> LLMResponse:
        # OR-specific 行为预留点（v0.3.x 后续可加 X-Title / fallback header 等）
        return self._inner.complete(req)

    async def acomplete(self, req: LLMRequest) -> LLMResponse:
        """v0.4.4 R-31：异步同样委托内核。"""
        return await self._inner.acomplete(req)


_check: LLMAdapter = OpenRouterAdapter()
