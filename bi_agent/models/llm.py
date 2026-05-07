"""LLM 调用契约 + 模型注册元数据。

代表的真实实体：
  - 一次发往 LLM provider 的 HTTP 请求 = LLMRequest
  - LLM 返回的文本 + token 使用量 = LLMResponse
  - 系统能调用的某个具体模型（如 claude-haiku-4-5） = ModelConfig

LLMAdapter Protocol（在 adapters/llm/base.py）以本模块的 dataclass 作输入输出契约。

Go 重写映射：internal/domain/llm.go（含 ProviderKind 枚举常量化）。
"""
from dataclasses import dataclass
from typing import Literal

ProviderKind = Literal[
    "openrouter", "anthropic", "openai",
    "deepseek", "google", "qwen", "zhipu", "minimax",
    "vllm", "ollama",  # v0.3.2 私有部署预留
]


@dataclass
class LLMMessage:
    """单条对话消息（OpenAI 风格 role/content）。"""
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMRequest:
    """发往 LLM provider 的完整请求。
    与 adapters/llm/base.py 的 LLMRequest 形状一致；模块边界刻意双份以保持
    adapters/ 不依赖 models/（adapters 是叶子层）。"""
    model: str
    system: str
    messages: list  # list[LLMMessage]
    max_tokens: int = 4096
    temperature: float = 0.0


@dataclass
class LLMResponse:
    """LLM provider 返回值；cost_usd 由 calculate_cost 后期填充。"""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ModelConfig:
    """系统可调用的一个 LLM 模型（来自 config/pricing 或 DB model_settings）。

    is_default：admin 通过 /api/admin/models/{key}/default 切换；
    enabled=False 时不出现在前端可选列表（admin/models 面板隐藏）。
    """
    key: str
    provider: ProviderKind
    input_price: float = 0.0   # USD per 1M tokens
    output_price: float = 0.0
    enabled: bool = True
    is_default: bool = False
