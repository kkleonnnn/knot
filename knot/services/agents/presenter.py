"""knot/services/agents/presenter.py — v0.5.2 起从 orchestrator.py 抽出。

源行号区间（v0.5.1 final 状态 orchestrator.py 535 行）：
- L406-441 _PRESENTER_SYS prompt
- L444-484 run_presenter (sync)
- L487-535 arun_presenter (async, 含 R-30 透传)

R-106 + 方案 1 延迟 import：与 clarifier.py 同模式 — 顶部 0 反向 import；
共享 helpers 在函数体内延迟 import 主文件。

v0.6.0 F2.7：`_PRESENTER_SYS` 默认值从 `knot/prompts/presenter.md` lazy load。
fail-soft：.md 缺失返空字符串（prompt_service.get_prompt 走 DB 兜底；R-PA-2.2）。
"""
import json
import pathlib

from knot.services import prompt_service as _prompts_mod

_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def _load_default_prompt(name: str) -> str:
    """v0.6.0 F2.7：读 knot/prompts/{name}.md 作为默认 system prompt。
    缺失或异常 → 空字符串（fail-soft；上层 prompt_service 走 DB 兜底）。"""
    try:
        return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""

_PRESENTER_SYS = _load_default_prompt("presenter")


def run_presenter(
    question: str,
    sql: str,
    rows: list,
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
            "business_rules": _business_rules(),
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


async def arun_presenter(
    question: str,
    sql: str,
    rows: list,
    model_key: str,
    api_key: str = "",
    openrouter_api_key: str = "",
) -> dict:
    """v0.4.4 R-24：run_presenter 的 async 版本。"""
    # R-106 方案 1：延迟 import 主文件 helpers
    from knot.models.errors import BIAgentError
    from knot.services.agents.orchestrator import (
        _allm,
        _business_rules,
        _date_block,
        _parse_json,
        _resolve,
        _today,
    )

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
            "business_rules": _business_rules(),
        },
    )
    try:
        # R-32 agent_kind='presenter'
        text, it, ot, cost = await _allm(
            model_key, key, cfg, sys_prompt,
            [{"role": "user", "content": user_msg}], max_tokens=512,
            agent_kind="presenter",
        )
        result = _parse_json(text)
    except BIAgentError:
        raise  # R-30：领域异常透传
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
