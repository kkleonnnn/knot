"""knot/services/agents/sql_planner_llm.py — v0.5.2 起从 sql_planner.py 抽出。

源行号区间（v0.5.1 final 状态）：
- L306-335 `_call_llm`（sync — Anthropic / OpenAI 兼容路径，非 R-26 budget gate）
- L338-376 `_acall_llm`（async — 含 v0.4.4 R-26-Senior budget gate + R-30 BIAgentError 透传）

R-106 单向依赖：本模块依赖 stdlib + knot.config + knot.adapters.llm + knot.models.errors
+ knot.services.budget_service；严禁反向 import sql_planner.py / 其他兄弟子模块。
R-99 不破坏 R-26 senior budget gate + R-30 BIAgentError 透传契约。
"""
from knot.config import MAX_TOKENS_PER_QUERY, PROVIDER_BASE_URLS


def _call_llm(model_key, api_key, model_cfg, system_prompt, messages) -> tuple[str, int, int]:
    provider = model_cfg["provider"]

    if provider == "anthropic":
        import anthropic
        base_url = PROVIDER_BASE_URLS.get("anthropic", "")
        client = anthropic.Anthropic(
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
        )
        resp = client.messages.create(
            model=model_key,
            max_tokens=MAX_TOKENS_PER_QUERY,
            temperature=0,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        return resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens
    else:
        import openai
        base_url = PROVIDER_BASE_URLS.get(provider, "")
        client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
        full_msgs = [{"role": "system", "content": system_prompt}] + messages
        resp = client.chat.completions.create(
            model=model_key, max_tokens=MAX_TOKENS_PER_QUERY, temperature=0, messages=full_msgs
        )
        raw = resp.choices[0].message.content or ""
        it = resp.usage.prompt_tokens if resp.usage else 0
        ot = resp.usage.completion_tokens if resp.usage else 0
        return raw, it, ot


async def _acall_llm(model_key, api_key, model_cfg, system_prompt, messages) -> tuple[str, int, int]:
    """v0.4.4 _call_llm 的 async 版本（ReAct 循环每步用）。

    - 走 adapters/llm/factory.get_async_adapter (R-31)
    - R-26-Senior：调用前 budget 守护（agent_kind='sql_planner'）
    - R-30：原 SDK 异常已由 adapter 包装为 BIAgentError 子类 → 透传给 ReAct 循环 catch
    """
    from knot.adapters.llm import LLMRequest, get_async_adapter
    from knot.models.errors import BIAgentError, BudgetExceededError, LLMNetworkError
    from knot.services import budget_service

    # R-26-Senior：每步 LLM 调用前 budget 守护（防 ReAct 循环烧钱）
    estimated_cost = MAX_TOKENS_PER_QUERY / 1_000_000 * (
        float(model_cfg.get("input_price", 0) or 0) + float(model_cfg.get("output_price", 0) or 0)
    )
    allowed, meta = budget_service.check_agent_per_call_budget("sql_planner", estimated_cost)
    if not allowed:
        raise BudgetExceededError(meta or {})

    provider = model_cfg["provider"]
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    req = LLMRequest(
        model_key=model_key,
        system=system_prompt,
        messages=list(messages),
        api_key=api_key,
        base_url=base_url,
        max_tokens=MAX_TOKENS_PER_QUERY,
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
    return resp.text, resp.input_tokens, resp.output_tokens
