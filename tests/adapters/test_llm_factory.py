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


def test_factory_unknown_falls_back_to_openai_compat():
    """私有部署 (vllm/ollama/qwen 等) 默认走 OpenAI-compat。"""
    a = get_adapter("vllm")
    assert isinstance(a, OpenAICompatAdapter)
    a2 = get_adapter("")
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
