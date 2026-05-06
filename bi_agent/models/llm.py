"""LLM 调用与计费领域模型。

LLMAdapter 协议（v0.3.2 落地）将以这些 dataclass 作为输入输出契约。
"""
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

ProviderKind = Literal[
    "openrouter", "anthropic", "openai",
    "deepseek", "google", "qwen", "zhipu", "minimax",
    "vllm", "ollama",  # v0.3.2 私有部署预留
]


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMRequest:
    model: str
    system: str
    messages: list  # list[LLMMessage]
    max_tokens: int = 4096
    temperature: float = 0.0


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ModelConfig:
    """单个模型的注册信息（来自 config/pricing 或 DB）。"""
    key: str
    provider: ProviderKind
    input_price: float = 0.0   # USD per 1M tokens
    output_price: float = 0.0
    enabled: bool = True
    is_default: bool = False
