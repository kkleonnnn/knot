"""bi_agent.adapters.llm.base — LLM 适配器契约（v0.3.2）

行为契约 1:1 对应 Go interface：

    type LLMAdapter interface {
        Complete(req LLMRequest) (LLMResponse, error)
    }

实现按 provider 分文件：
  - anthropic_native.py : 直连 Anthropic SDK（messages API + cache_control）
  - openai_compat.py    : OpenAI-compatible（GPT / Gemini / DeepSeek / Ollama）
  - openrouter.py       : OpenRouter 统一路由（OR 内部走 OpenAI 兼容协议）
  - factory.py          : by ModelConfig.provider 路由
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMRequest:
    """LLMAdapter 的输入契约。
    存在意义：和 models/llm.py 的 LLMRequest 一致；adapters 内部使用以避免
    cross-layer import（adapters 可以 import models，但本 dataclass 把
    adapter 内部需要的字段做最小集合，便于 Go 重写时直接 1:1 映射 struct）。"""
    model_key: str
    system: str
    messages: list  # list[{"role": "user|assistant", "content": str}]
    api_key: str
    base_url: str = ""
    max_tokens: int = 1024
    temperature: float = 0.0
    enable_prompt_cache: bool = True


@dataclass
class LLMResponse:
    """LLMAdapter 的输出契约。"""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM 调用契约。"""

    def complete(self, req: LLMRequest) -> LLMResponse:
        """单次同步 completion；失败必须抛异常（不返 sentinel value）。"""
        ...


# ── 成本计算（与 provider 无关的纯函数；放在本契约模块作便捷工具）─────
def calculate_cost(input_tokens: int, output_tokens: int,
                   input_price: float, output_price: float) -> float:
    """USD = (in_tokens * in_price + out_tokens * out_price) / 1_000_000"""
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
