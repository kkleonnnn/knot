"""bi_agent.adapters.llm.async_base — v0.4.4 真异步 LLM 调用预留接口。

v0.4.0 仅锁形状（Protocol 定义 + dataclass 复用）；v0.4.4 落 impl 时所有
LLMAdapter 实现都需要补 acomplete()，并把 services/llm_client._invoke_via_adapter
切到 await get_async_adapter(provider).acomplete(req)。

Go 重写映射：
    type AsyncLLMAdapter interface {
        CompleteAsync(ctx context.Context, req LLMRequest) (LLMResponse, error)
    }

当前阶段任何 adapter 都可以不实现 acomplete，运行时不调用即可（同步路径仍走
LLMAdapter.complete）。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from bi_agent.adapters.llm.base import LLMRequest, LLMResponse


@runtime_checkable
class AsyncLLMAdapter(Protocol):
    """v0.4.4 落地的异步契约。

    实现端注意：
    - 必须使用 httpx.AsyncClient / AsyncOpenAI / AsyncAnthropic 等真异步客户端
    - 不得在内部 run_in_executor 同步 SDK（这是当前 services/llm_client.py
      的临时桥接做法，v0.4.4 必须根除）
    - 失败抛异常（与同步版一致），调用方负责重试 / 降级
    """

    async def acomplete(self, req: LLMRequest) -> LLMResponse:
        """单次异步 completion。"""
        ...
