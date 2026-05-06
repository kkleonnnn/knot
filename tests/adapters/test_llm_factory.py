"""adapters/llm/factory happy-path 单测。"""
from bi_agent.adapters.llm.anthropic_native import AnthropicAdapter
from bi_agent.adapters.llm.base import LLMAdapter, LLMRequest, calculate_cost
from bi_agent.adapters.llm.factory import get_adapter
from bi_agent.adapters.llm.openai_compat import OpenAICompatAdapter
from bi_agent.adapters.llm.openrouter import OpenRouterAdapter


def test_factory_anthropic():
    a = get_adapter("anthropic")
    assert isinstance(a, AnthropicAdapter)
    assert isinstance(a, LLMAdapter)


def test_factory_openrouter():
    a = get_adapter("openrouter")
    assert isinstance(a, OpenRouterAdapter)
    assert isinstance(a, LLMAdapter)


def test_factory_openai_default():
    a = get_adapter("openai")
    assert isinstance(a, OpenAICompatAdapter)


def test_factory_known_private_deploy_providers():
    """已显式登记的私有部署 provider（vllm / ollama）走 OpenAI-compat。
    v0.3.2 R-7 之前空字符串会兜底；现在改为显式抛 ProviderNotImplementedError
    （由 test_factory_unknown_provider_raises 验证）。"""
    a = get_adapter("vllm")
    assert isinstance(a, OpenAICompatAdapter)
    a2 = get_adapter("ollama")
    assert isinstance(a2, OpenAICompatAdapter)


def test_factory_case_insensitive():
    assert isinstance(get_adapter("ANTHROPIC"), AnthropicAdapter)
    assert isinstance(get_adapter("OpenRouter"), OpenRouterAdapter)


def test_calculate_cost_zero_tokens():
    assert calculate_cost(0, 0, 1.0, 2.0) == 0.0


def test_calculate_cost_basic():
    # 1M input × 0.5 + 1M output × 2.0 = 0.5 + 2.0 = 2.5
    assert calculate_cost(1_000_000, 1_000_000, 0.5, 2.0) == 2.5


def test_llm_request_dataclass_defaults():
    r = LLMRequest(model_key="m", system="s", messages=[], api_key="k")
    assert r.max_tokens == 1024
    assert r.temperature == 0.0
    assert r.enable_prompt_cache is True
    assert r.base_url == ""


def test_protocol_runtime_check_rejects_non_adapter():
    """LLMAdapter 是 runtime_checkable Protocol；缺少 complete 应失败。"""
    class NotAnAdapter:
        pass

    assert not isinstance(NotAnAdapter(), LLMAdapter)


# ── R-7：factory 严格化（未知 provider 抛 ProviderNotImplementedError）──

def test_factory_unknown_provider_raises():
    """v0.3.2 R-7：传 typo provider 必须显式失败，不再 silently fallback。"""
    import pytest
    from bi_agent.models.errors import ProviderNotImplementedError

    with pytest.raises(ProviderNotImplementedError) as exc_info:
        get_adapter("anthropics-typo")
    err = exc_info.value
    assert err.provider == "anthropics-typo"
    assert "anthropic" in err.supported
    assert "openrouter" in err.supported


def test_factory_known_openai_compat_providers():
    """已知走 OpenAI-compat 协议的 provider 都能解析（gemini/deepseek/qwen/glm 等）。"""
    for p in ("openai", "gemini", "google", "deepseek", "qwen", "zhipu",
              "glm", "minimax", "ollama", "vllm"):
        a = get_adapter(p)
        assert isinstance(a, OpenAICompatAdapter), f"provider {p!r} should be OpenAI-compat"


# ── R-9：显式 Protocol 类型注解作为函数签名——验证"面向接口编程" ──

def test_function_accepts_protocol_typed_argument():
    """证明 Protocol 不是装饰，是真实可作类型签名的契约。
    任何 LLMAdapter 实现都应能传入 take_adapter()。"""
    def take_adapter(a: LLMAdapter) -> str:
        # 函数体内只调用 Protocol 声明的方法，不应假定具体类
        return type(a).__name__

    assert take_adapter(get_adapter("anthropic")) == "AnthropicAdapter"
    assert take_adapter(get_adapter("openrouter")) == "OpenRouterAdapter"
    assert take_adapter(get_adapter("openai")) == "OpenAICompatAdapter"
