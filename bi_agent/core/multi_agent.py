"""
multi_agent.py — 3-Agent Orchestrator (Clarifier / SQL Planner / Presenter)
SQL Planner reuses the existing sql_agent.run_sql_agent().
v0.2.2: Validator agent removed; Presenter prompt now does light anomaly check inline.
"""

import json
import re

import llm_client
import prompts as _prompts_mod
import date_context

try:
    from ohx_catalog import BUSINESS_RULES as _OHX_RULES
except Exception:
    _OHX_RULES = ""


def _today() -> str:
    return date_context.today_iso()


def _date_block() -> str:
    return date_context.date_context_block()
from config import (
    MODELS, DEFAULT_MODEL,
    PROVIDER_API_KEYS, PROVIDER_BASE_URLS,
)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _app_or_key() -> str:
    try:
        import persistence
        return persistence.get_app_setting("openrouter_api_key", "") or ""
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


# ── Agent 1: Clarifier ─────────────────────────────────────────────────────────

_CLARIFIER_SYS = """你是数据分析助手的「问题理解专家」。
判断用户问题是否明确可执行，并给出精确化的查询描述。

{date_block}

{business_rules}

业务规则消歧（重要）：
- "昨天/今天" 指业务日（UTC+8 14:00 切日），不是自然日 [00:00, 24:00)
- "用户/真实用户" 默认排除测试号；上方业务规则有完整 user_id 范围
- "充值/提现金额" 未指明币种 → 默认 USDT
- 用户提到"周报/月报/本周/上月"时，refined_question 中必须保留这些词，提示 sql_planner 切换聚合表

输出严格 JSON（禁止任何其他内容）：
{
  "is_clear": true,
  "clarification_question": null,
  "refined_question": "精确化后的完整问题描述",
  "analysis_approach": "一句话说明分析思路"
}

is_clear 为 false 仅当：核心指标存在多种完全不同的解释（如"利润"可能是净利润或手续费），且这些解释会导致完全不同的 SQL。
注意：下方 Schema 包含字段名+注释，若字段注释能直接对应问题中的概念（如"注册用户"对应 user.created_at），视为 is_clear=true，不要追问。
如对话历史中已有澄清回复，直接视为 is_clear=true 并将澄清信息融入 refined_question。

代词解析（强制规则）：用户用「这些」「上述」「刚才的」「他们」「那批」等指代词时：
1. 必须结合 history 中上一条 Q+SQL+结果定位到具体口径
2. is_clear=true，把口径完整写入 refined_question（如"列出 2026-04-25 注册的用户ID"）
3. 禁止以"上一题用的是聚合表/没有明细字段/数据库中是否存在 xx 表"为由追问 —— 这些是 sql_planner 的责任，不是澄清范围；找不到合适表由 sql_planner 报错
4. 数据源/表选择的疑虑写到 analysis_approach 里供下游参考，不要写到 clarification_question
5. 仅当 history 为空且代词无法从字面推断时才追问

正确示例：
  history Q: "2026-04-25 注册用户数" → SQL 用 ads_operation_report_daily.reg_user_num=8
  当前 Q: "把这些用户的ID列一下"
  正确输出：{"is_clear": true, "refined_question": "列出 2026-04-25 当天注册的用户的 ID", "analysis_approach": "上一题用的是聚合表无 ID，需 sql_planner 在 dwd/ods 层找用户注册明细表"}

Schema（表 / 字段 / 注释）：
{schema}

对话历史：
{history}"""


def run_clarifier(
    question: str,
    schema_text: str,
    history: list,
    model_key: str,
    api_key: str = "",
    openrouter_api_key: str = "",
) -> dict:
    # v0.2.1 修复 clarifier 字段盲区：传完整 schema（含字段名+注释），上限 6000 字防超 token
    schema_slice = (schema_text or "")[:6000] or "(无 Schema)"
    # v0.2.1 批次4：history 同时给出上一次的 SQL 与结果摘要，让 clarifier 能解析
    # 「这些用户」「上述」「刚才的」等代词，避免追问已可推断的上下文
    if history:
        lines = []
        for h in history[-3:]:
            q = h.get("question", "")
            sql = (h.get("sql") or "").strip().replace("\n", " ")
            rows = h.get("rows") or []
            if sql:
                sql_short = sql if len(sql) <= 220 else sql[:220] + "…"
                sample = json.dumps(rows[:2], ensure_ascii=False, default=str) if rows else "[]"
                lines.append(f"Q: {q}\n  SQL: {sql_short}\n  结果(前2行,共{len(rows)}行): {sample}")
            else:
                lines.append(f"Q: {q}")
        history_text = "\n".join(lines)
    else:
        history_text = "无"
    system = _prompts_mod.get_prompt(
        "clarifier", _CLARIFIER_SYS,
        {
            "schema": schema_slice, "history": history_text,
            "today": _today(), "date_block": _date_block(),
            "business_rules": _OHX_RULES,
        },
    )

    model_key, key, cfg = _resolve(model_key, api_key, openrouter_api_key)
    it = ot = 0
    cost = 0.0
    result = {}
    try:
        text, it, ot, cost = _llm(model_key, key, cfg, system,
                                   [{"role": "user", "content": question}], max_tokens=300)
        result = _parse_json(text)
    except Exception:
        pass

    return {
        "is_clear": result.get("is_clear", True),
        "clarification_question": result.get("clarification_question"),
        "refined_question": result.get("refined_question", question),
        "analysis_approach": result.get("analysis_approach", ""),
        "input_tokens": it,
        "output_tokens": ot,
        "cost_usd": cost,
    }


# ── Agent 3: Presenter ─────────────────────────────────────────────────────────

_PRESENTER_SYS = """你是数据洞察专家。根据用户问题和查询结果，给出简洁的分析洞察，并推荐高价值的追问方向。
同时承担轻量结果质量检查：发现数据可能存在异常时，在 insight 开头加 ⚠️ 并简述疑点，但仍要给出洞察、不要拒绝输出。

{date_block}

{business_rules}

输出严格 JSON：
{
  "insight": "2-3句分析洞察，直接点出关键发现、趋势或异常；如有疑点用 ⚠️ 开头",
  "confidence": "high",
  "suggested_followups": ["追问方向1", "追问方向2"]
}

confidence 含义：
- "high"：结果符合预期、数据可信
- "medium"：有轻微疑点（数据偏少、量级略异常）但基本可用
- "low"：结果明显异常（应有数据却为空、数值量级离谱、时间范围错位）

异常判断规则：
- 应有数据却空集（如查"昨天的订单数"返回 0 行）→ confidence=low，insight 用 ⚠️ 开头说明可能原因
- 全 0 / 全 NULL 的聚合结果 → confidence=low
- ≤ 今日的日期是历史日期，不要判定为"未来"
- 单聚合标量结果（COUNT/SUM）非 0 即 high

幻觉禁令（必须严格遵守）：
- 禁止臆造权限错误：你拿到的 SQL 已经成功执行；输入里如果没有"执行失败/Access denied/permission denied"等字样，就**不准**说"没有权限""无访问权限""权限不足"。
- 空结果集只能解释为"该口径下数据为 0 / 表里没有满足条件的数据 / 时间范围内无业务发生"，不要归因到权限。
- 不要在 insight 里编造未在结果中出现的字段值或表名；引用数字必须来自查询结果。
- 不要替用户切换日期口径：如果用户问"昨天"，不要在 insight 里说"实际查询了去年同日"。

结果为空时，insight 说明可能原因（数据真的为零 / 时间窗口外 / 口径过严）并给出排查建议。
suggested_followups 给出 2 个最有价值的下一步分析方向（简洁，不超过 15 字）。
洞察用动词开头（或 ⚠️ 开头），不超过 3 句。"""


def run_presenter(
    question: str,
    sql: str,
    rows: list,
    model_key: str,
    api_key: str = "",
    openrouter_api_key: str = "",
) -> dict:
    sample = json.dumps(rows[:10], ensure_ascii=False, default=str) if rows else "[]"
    user_msg = (
        f"问题：{question}\n"
        f"SQL：{sql or '(无)'}\n"
        f"查询结果（前10行，共 {len(rows)} 行）：{sample}"
    )

    model_key, key, cfg = _resolve(model_key, api_key, openrouter_api_key)
    it = ot = 0
    cost = 0.0
    result = {}
    sys_prompt = _prompts_mod.get_prompt(
        "presenter", _PRESENTER_SYS,
        {
            "today": _today(), "date_block": _date_block(),
            "business_rules": _OHX_RULES,
        },
    )
    try:
        text, it, ot, cost = _llm(model_key, key, cfg, sys_prompt,
                                   [{"role": "user", "content": user_msg}], max_tokens=512)
        result = _parse_json(text)
    except Exception:
        pass

    return {
        "insight": result.get("insight", ""),
        "confidence": result.get("confidence", "high"),
        "suggested_followups": result.get("suggested_followups", []),
        "input_tokens": it,
        "output_tokens": ot,
        "cost_usd": cost,
    }
