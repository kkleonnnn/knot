"""knot/services/agents/clarifier.py — v0.5.2 起从 orchestrator.py 抽出。

源行号 (v0.5.1 final L535)：L15-34 intent 常量 / L198-268 prompt / L271-329 sync / L332-403 async。
R-106 方案 1：函数体内延迟 import 主文件 helpers（避免 import-time 循环 + monkeypatch 自动生效）。

v0.6.0 F2.6：`_CLARIFIER_SYS` 默认值从 `knot/prompts/clarifier.md` lazy load。
fail-soft：.md 缺失返空字符串（prompt_service.get_prompt 走 DB 兜底；R-PA-2.2）。
"""
import json
import pathlib

from knot.services import prompt_service as _prompts_mod

_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def _load_default_prompt(name: str) -> str:
    """v0.6.0 F2.6：读 knot/prompts/{name}.md 作为默认 system prompt。
    缺失或异常 → 空字符串（fail-soft；上层 prompt_service 走 DB 兜底）。"""
    try:
        return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""

# ── v0.4.0 Intent 枚举 + 前端 layout 映射（detail > retention > rank > compare > trend > distribution > metric） ──
VALID_INTENTS: tuple[str, ...] = (
    "metric", "trend", "compare", "rank", "distribution", "retention", "detail",
)

INTENT_TO_HINT: dict[str, str] = {
    "metric": "metric_card", "trend": "line", "compare": "bar", "rank": "rank_view",
    "distribution": "pie", "retention": "retention_matrix", "detail": "detail_table",
}

DEFAULT_INTENT_FALLBACK: str = "detail"


_CLARIFIER_SYS = _load_default_prompt("clarifier")


def _render_clarifier_inputs(schema_text: str, history: list) -> tuple[str, str]:
    """sync/async 共用：组装 schema_slice + history_text。"""
    schema_slice = (schema_text or "")[:6000] or "(无 Schema)"
    if not history:
        return schema_slice, "无"
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
    return schema_slice, "\n".join(lines)


def _build_clarifier_result(question: str, result: dict, it: int, ot: int, cost: float) -> dict:
    """sync/async 共用：组装 clarifier 返回 dict + intent fallback (V-INTENTS)。"""
    raw_intent = result.get("intent")
    intent = raw_intent if raw_intent in VALID_INTENTS else DEFAULT_INTENT_FALLBACK
    return {
        "is_clear": result.get("is_clear", True),
        "clarification_question": result.get("clarification_question"),
        "refined_question": result.get("refined_question", question),
        "analysis_approach": result.get("analysis_approach", ""),
        "intent": intent,
        "input_tokens": it,
        "output_tokens": ot,
        "cost_usd": cost,
    }


def run_clarifier(
    question: str,
    schema_text: str,
    history: list,
    model_key: str,
    api_key: str = "",
    openrouter_api_key: str = "",
) -> dict:
    """[DEPRECATED v0.5.5; target removal in v1.0] Use async equivalent (a*) instead."""
    # R-106 方案 1：延迟 import 主文件 helpers
    from knot.services.agents.orchestrator import (
        _business_rules,
        _date_block,
        _llm,
        _parse_json,
        _resolve,
        _today,
    )

    schema_slice, history_text = _render_clarifier_inputs(schema_text, history)
    system = _prompts_mod.get_prompt(
        "clarifier", _CLARIFIER_SYS,
        {
            "schema": schema_slice, "history": history_text,
            "today": _today(), "date_block": _date_block(),
            "business_rules": _business_rules(),
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

    return _build_clarifier_result(question, result, it, ot, cost)


async def arun_clarifier(
    question: str,
    schema_text: str,
    history: list,
    model_key: str,
    api_key: str = "",
    openrouter_api_key: str = "",
) -> dict:
    """v0.4.4 R-24：async 版；走 _allm（R-26-Senior + R-30）+ R-32 agent_kind='clarifier'。"""
    # R-106 方案 1：延迟 import
    from knot.models.errors import BIAgentError
    from knot.services.agents.orchestrator import (
        _allm,
        _business_rules,
        _date_block,
        _parse_json,
        _resolve,
        _today,
    )

    schema_slice, history_text = _render_clarifier_inputs(schema_text, history)
    system = _prompts_mod.get_prompt(
        "clarifier", _CLARIFIER_SYS,
        {
            "schema": schema_slice, "history": history_text,
            "today": _today(), "date_block": _date_block(),
            "business_rules": _business_rules(),
        },
    )

    model_key, key, cfg = _resolve(model_key, api_key, openrouter_api_key)
    it = ot = 0
    cost = 0.0
    result = {}
    try:
        text, it, ot, cost = await _allm(
            model_key, key, cfg, system,
            [{"role": "user", "content": question}], max_tokens=300,
            agent_kind="clarifier",
        )
        result = _parse_json(text)
    except BIAgentError:
        # R-30：领域异常透传（BudgetExceededError / LLMAuthError 等不可吞）
        raise
    except Exception:
        # 非领域异常静默：与 sync 版本同模式，避免单步失败炸整流
        pass

    return _build_clarifier_result(question, result, it, ot, cost)
