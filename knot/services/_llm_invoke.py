"""knot/services/_llm_invoke.py — v0.5.2 起从 llm_client.py 抽出。

源行号区间（v0.5.1 final 状态 llm_client.py 574 行）：
- L303-329 `_invoke_via_adapter` (sync)
- L334-358 `_parse_llm_response`
- L361-368 `_normalize_result`
- L371-375 `_error_result`
- L380-381 `calculate_cost`（service 层；与 adapters.llm.calculate_cost 同语义独立保留）
- L419-428 `_estimate_cost_for_budget_check`
- L431-479 `_ainvoke_via_adapter` (async, 含 v0.4.4 R-26 senior budget gate + R-30 透传)

R-106 单向依赖：本模块依赖 stdlib + knot.config + knot.adapters.llm + knot.models.errors
+ delayed knot.services.budget_service；严禁反向 import knot.services.llm_client / 其他兄弟。
R-100 R-108 关键：calculate_cost 由 llm_client.py re-export 给 sql_planner / orchestrator
通过 `llm_client.calculate_cost(...)` 调用 — Token 计费路径迁移后不变。
"""
import json
import re

from knot.adapters.llm import LLMRequest, get_adapter, get_async_adapter
from knot.config import (
    MAX_TOKENS_PER_QUERY,
    PROVIDER_BASE_URLS,
    SQL_TEMPERATURE,
)
from knot.models.errors import (
    BIAgentError,
    BudgetExceededError,
    LLMAuthError,
    LLMNetworkError,
    LLMRateLimitError,
)

# ── Cost calculation ───────────────────────────────────────────────────

def calculate_cost(input_tokens, output_tokens, input_price, output_price) -> float:
    return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)


def _estimate_cost_for_budget_check(model_cfg: dict) -> float:
    """v0.4.4 R-26-Senior：预估单次调用 cost 上限（在 LLM 请求前用于 budget 守护）。

    策略：用 MAX_TOKENS_PER_QUERY 作 output 上限 + 同等量级 input → 粗略上限估算。
    实际 cost 一般低于此估算（input 通常 < 5K tokens；output 受 max_tokens 限制）。
    宁可估高不估低 — block 偏严而非偏松。
    """
    in_price = float(model_cfg.get("input_price", 0) or 0)
    out_price = float(model_cfg.get("output_price", 0) or 0)
    return MAX_TOKENS_PER_QUERY / 1_000_000 * (in_price + out_price)


# ── JSON parsing ───────────────────────────────────────────────────────

def _parse_llm_response(raw_text: str) -> dict:
    text = raw_text.strip()
    try:
        return _normalize_result(json.loads(text))
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return _normalize_result(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    for m in sorted(re.findall(r"\{[\s\S]*?\}", text, re.DOTALL), key=len, reverse=True):
        try:
            return _normalize_result(json.loads(m))
        except json.JSONDecodeError:
            continue

    return {
        "sql": "", "explanation": "", "confidence": "low",
        "error": f"无法解析 LLM 输出: {text[:300]}",
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


def _normalize_result(result: dict) -> dict:
    return {
        "sql":          result.get("sql", ""),
        "explanation":  result.get("explanation", ""),
        "confidence":   result.get("confidence", "low"),
        "error":        result.get("error", ""),
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


def _error_result(message: str) -> dict:
    return {
        "sql": "", "explanation": "", "confidence": "low", "error": message,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }


# ── Provider calls (sync + async) ──────────────────────────────────────

def _invoke_via_adapter(system_prompt: str, user_message: str,
                        model_key: str, api_key: str, model_cfg: dict, provider: str) -> dict:
    """[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead.

    统一走 adapters/llm/factory；provider 路由 + 错误友好转换 + cost 计算。
    """
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    req = LLMRequest(
        model_key=model_key,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        api_key=api_key,
        base_url=base_url,
        max_tokens=MAX_TOKENS_PER_QUERY,
        temperature=SQL_TEMPERATURE,
        enable_prompt_cache=(provider == "anthropic"),
    )
    try:
        resp = get_adapter(provider).complete(req)
    except RuntimeError as e:
        return _error_result(str(e))

    parsed = _parse_llm_response(resp.text)
    parsed["input_tokens"] = resp.input_tokens
    parsed["output_tokens"] = resp.output_tokens
    parsed["cost_usd"] = calculate_cost(
        resp.input_tokens, resp.output_tokens,
        model_cfg["input_price"], model_cfg["output_price"],
    )
    return parsed


async def _ainvoke_via_adapter(system_prompt: str, user_message: str,
                                model_key: str, api_key: str, model_cfg: dict, provider: str,
                                *, agent_kind: str = "sql_planner") -> dict:
    """v0.4.4 真异步 LLM 调用入口。

    R-26-Senior：第一行先做 budget per_call 守护（早于 SDK 实例化 / 网络连接）；
    没钱时连 0 字节网络成本都不产生 → 抛 BudgetExceededError。
    R-32：agent_kind 默认 'sql_planner'，afix_sql 必须显式传 'fix_sql'，
    使分桶 cost 累加到 fix_sql_cost 桶（query.py 流程不变）。
    R-30：原 SDK 异常已由 adapter 包装为 LLMAuthError / LLMRateLimitError /
    LLMNetworkError；本函数捕获 BIAgentError 转 _error_result（保留 sync API 兼容）。
    """
    # R-26-Senior：budget block 在 LLM 请求前；延迟 import 避开 v0.3.x 启动期循环依赖
    from knot.services import budget_service
    estimated_cost = _estimate_cost_for_budget_check(model_cfg)
    allowed, meta = budget_service.check_agent_per_call_budget(agent_kind, estimated_cost)
    if not allowed:
        raise BudgetExceededError(meta or {})

    base_url = PROVIDER_BASE_URLS.get(provider, "")
    req = LLMRequest(
        model_key=model_key,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        api_key=api_key,
        base_url=base_url,
        max_tokens=MAX_TOKENS_PER_QUERY,
        temperature=SQL_TEMPERATURE,
        enable_prompt_cache=(provider == "anthropic"),
    )
    try:
        adapter = get_async_adapter(provider)
        resp = await adapter.acomplete(req)
    except (LLMAuthError, LLMRateLimitError, LLMNetworkError):
        raise  # adapter 已分类；上层 api/query.py 用 error_translator 翻译
    except BIAgentError:
        raise
    except Exception as e:
        # 非领域异常兜底（理论不应发生，因为 adapter 应已包装）
        raise LLMNetworkError(str(e)[:200]) from e

    parsed = _parse_llm_response(resp.text)
    parsed["input_tokens"] = resp.input_tokens
    parsed["output_tokens"] = resp.output_tokens
    parsed["cost_usd"] = calculate_cost(
        resp.input_tokens, resp.output_tokens,
        model_cfg["input_price"], model_cfg["output_price"],
    )
    return parsed
