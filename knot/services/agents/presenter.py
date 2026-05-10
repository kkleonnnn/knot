"""knot/services/agents/presenter.py — v0.5.2 起从 orchestrator.py 抽出。

源行号区间（v0.5.1 final 状态 orchestrator.py 535 行）：
- L406-441 _PRESENTER_SYS prompt
- L444-484 run_presenter (sync)
- L487-535 arun_presenter (async, 含 R-30 透传)

R-106 + 方案 1 延迟 import：与 clarifier.py 同模式 — 顶部 0 反向 import；
共享 helpers 在函数体内延迟 import 主文件。
"""
import json

from knot.services import prompt_service as _prompts_mod

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
