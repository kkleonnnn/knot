"""
multi_agent.py — 3-Agent Orchestrator (Clarifier / SQL Planner / Presenter)

v0.5.2 拆分：本主文件作"调度员 + 共享 helpers 容器"
- clarifier.py: VALID_INTENTS + INTENT_TO_HINT + DEFAULT_INTENT_FALLBACK + _CLARIFIER_SYS
                + run_clarifier + arun_clarifier
- presenter.py: _PRESENTER_SYS + run_presenter + arun_presenter
- 主文件保留：_resolve / _llm / _allm / _parse_json / _today / _date_block
              / _business_rules / _app_or_key
              （子文件函数体内延迟 import 主文件 helpers — R-106 方案 1）

v0.4.0 历史：Clarifier 输出新增 intent 字段（7 类）+ INTENT_TO_HINT 映射；
前端按 intent 分支渲染 layout（clarifier.py 内承载常量定义）。
SQL Planner reuses sql_planner.run_sql_agent() / arun_sql_agent().
v0.2.2 历史：Validator agent removed; Presenter prompt now does light anomaly check inline.

R-100 re-export：测试 `monkeypatch.setattr(orchestrator, "_allm", spy)` + 业务侧
`orchestrator.run_clarifier()` / `orchestrator.INTENT_TO_HINT` 调用路径不变。
"""

import json
import re

from knot.core import date_context
from knot.services import llm_client

try:
    from knot.services.agents import catalog as _cl
except Exception:
    _cl = None


def _business_rules() -> str:
    return getattr(_cl, "BUSINESS_RULES", "") if _cl else ""


def _today() -> str:
    return date_context.today_iso()


def _date_block() -> str:
    return date_context.date_context_block()


from knot.config import (  # noqa: E402  legacy import order；v0.3.x 不强制重排
    DEFAULT_MODEL,
    MODELS,
    PROVIDER_API_KEYS,
    PROVIDER_BASE_URLS,
)

# v0.5.2 R-100 re-export — 测试 + 业务 import 路径 0 修改
from knot.services.agents.clarifier import (  # noqa: E402, F401  re-export
    DEFAULT_INTENT_FALLBACK,
    INTENT_TO_HINT,
    VALID_INTENTS,
    arun_clarifier,
    run_clarifier,
)
from knot.services.agents.presenter import (  # noqa: E402, F401  re-export
    arun_presenter,
    run_presenter,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────

def _app_or_key() -> str:
    try:
        from knot.repositories.settings_repo import get_app_setting
        return get_app_setting("openrouter_api_key", "") or ""
    except Exception:
        return ""


def _resolve(model_key: str, api_key: str = "", openrouter_api_key: str = ""):
    """Return (resolved_model_key, api_key, model_cfg).
    OR key fallback chain: explicit arg → app_settings → env (PROVIDER_API_KEYS).
    """
    registered = MODELS.get(model_key)
    if registered and registered.get("provider") == "openrouter":
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        return model_key, key, registered
    if "/" in model_key and not registered:
        key = openrouter_api_key or _app_or_key() or PROVIDER_API_KEYS.get("openrouter", "")
        cfg = {"provider": "openrouter", "input_price": 0.0, "output_price": 0.0}
        return model_key, key, cfg
    cfg = registered
    if not cfg:
        model_key = DEFAULT_MODEL
        cfg = MODELS[model_key]
    key = api_key or PROVIDER_API_KEYS.get(cfg["provider"], "")
    return model_key, key, cfg


def _llm(model_key: str, key: str, cfg: dict, system: str, messages: list, max_tokens: int = 400):
    """Single LLM call; returns (text, input_tokens, output_tokens, cost_usd)."""
    provider = cfg["provider"]
    if provider == "anthropic":
        import anthropic
        base_url = PROVIDER_BASE_URLS.get("anthropic", "")
        client = anthropic.Anthropic(
            api_key=key,
            **({"base_url": base_url} if base_url else {}),
        )
        resp = client.messages.create(
            model=model_key, max_tokens=max_tokens, temperature=0,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        text = resp.content[0].text
        it, ot = resp.usage.input_tokens, resp.usage.output_tokens
    else:
        import openai
        base_url = PROVIDER_BASE_URLS.get(provider, "")
        client = openai.OpenAI(api_key=key, base_url=base_url or None)
        resp = client.chat.completions.create(
            model=model_key, max_tokens=max_tokens, temperature=0,
            messages=[{"role": "system", "content": system}] + messages,
        )
        text = resp.choices[0].message.content or ""
        it = resp.usage.prompt_tokens if resp.usage else 0
        ot = resp.usage.completion_tokens if resp.usage else 0

    cost = llm_client.calculate_cost(it, ot, cfg.get("input_price", 0), cfg.get("output_price", 0))
    return text, it, ot, cost


async def _allm(model_key: str, key: str, cfg: dict, system: str, messages: list,
                max_tokens: int = 400, *, agent_kind: str = "clarifier"):
    """v0.4.4 _llm 的 async 版本。
    - 走 adapters/llm/factory.get_async_adapter（R-31 守护）
    - R-26-Senior：调用前先做 budget per_call 守护（与 llm_client._ainvoke_via_adapter 同模式）
    - R-32：agent_kind 由调用方传（arun_clarifier='clarifier' / arun_presenter='presenter'）
    - R-30：原 SDK 异常已由 adapter 包装为 LLMAuthError / LLMRateLimitError / LLMNetworkError；
      上游 catch BIAgentError 用 error_translator 翻译。
    返回 (text, input_tokens, output_tokens, cost_usd)。
    """
    from knot.adapters.llm import LLMRequest, get_async_adapter
    from knot.models.errors import (
        BIAgentError,
        BudgetExceededError,
        LLMNetworkError,
    )
    from knot.services import budget_service

    # R-26-Senior：在 LLM 请求之前 budget 守护
    estimated_cost = max_tokens / 1_000_000 * (
        float(cfg.get("input_price", 0) or 0) + float(cfg.get("output_price", 0) or 0)
    )
    allowed, meta = budget_service.check_agent_per_call_budget(agent_kind, estimated_cost)
    if not allowed:
        raise BudgetExceededError(meta or {})

    provider = cfg["provider"]
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    req = LLMRequest(
        model_key=model_key,
        system=system,
        messages=messages,
        api_key=key,
        base_url=base_url,
        max_tokens=max_tokens,
        temperature=0,
        enable_prompt_cache=(provider == "anthropic"),
    )
    try:
        adapter = get_async_adapter(provider)
        resp = await adapter.acomplete(req)
    except BIAgentError:
        raise
    except Exception as e:
        raise LLMNetworkError(str(e)[:200]) from e

    cost = llm_client.calculate_cost(
        resp.input_tokens, resp.output_tokens,
        cfg.get("input_price", 0), cfg.get("output_price", 0),
    )
    return resp.text, resp.input_tokens, resp.output_tokens, cost


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r'\{[\s\S]+\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}
