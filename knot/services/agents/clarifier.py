"""knot/services/agents/clarifier.py — v0.5.2 起从 orchestrator.py 抽出。

源行号 (v0.5.1 final L535)：L15-34 intent 常量 / L198-268 prompt / L271-329 sync / L332-403 async。
R-106 方案 1：函数体内延迟 import 主文件 helpers（避免 import-time 循环 + monkeypatch 自动生效）。
"""
import json

from knot.services import prompt_service as _prompts_mod

# ── v0.4.0 Intent 枚举 + 前端 layout 映射（detail > retention > rank > compare > trend > distribution > metric） ──
VALID_INTENTS: tuple[str, ...] = (
    "metric", "trend", "compare", "rank", "distribution", "retention", "detail",
)

INTENT_TO_HINT: dict[str, str] = {
    "metric": "metric_card", "trend": "line", "compare": "bar", "rank": "rank_view",
    "distribution": "pie", "retention": "retention_matrix", "detail": "detail_table",
}

DEFAULT_INTENT_FALLBACK: str = "detail"


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
  "analysis_approach": "一句话说明分析思路",
  "intent": "metric"
}

is_clear 为 false 仅当：核心指标存在多种完全不同的解释（如"利润"可能是净利润或手续费），且这些解释会导致完全不同的 SQL。
注意：下方 Schema 包含字段名+注释，若字段注释能直接对应问题中的概念（如"注册用户"对应 user.created_at），视为 is_clear=true，不要追问。
如对话历史中已有澄清回复，直接视为 is_clear=true 并将澄清信息融入 refined_question。

意图分类（intent 字段 — 必填，7 类必选其一）：
- metric         : 用户问"是多少 / 总和 / 平均"，期望单一聚合值
- trend          : 用户问"近 N 天 / 最近一段时间 / 每日/每周/每月趋势"，期望时间序列
- compare        : 用户问"A vs B / 同比 / 环比 / 对比"，期望两组或多组对照
- rank           : 用户问"Top N / 最大/最小/前几 / 排行"，期望排序后取前 N
- distribution   : 用户问"分布 / 占比 / 各 X 多少"（不强调排序），期望桶式聚合
- retention      : 用户问"留存 / 次日 / 7日 / 30日活跃"，期望留存矩阵
- detail         : 用户问"列出 / 列表 / 明细 / ID / 给我 X 条"，期望原始记录

判定优先级（多种语义共存时按 leftmost match 取）：
detail > retention > rank > compare > trend > distribution > metric

特殊规则：
- 用户提及"导出 / 下载 / CSV / 表格" → 强制 detail
- 用户用"上述/这些用户/这些 ID"等代词指代具体记录 → 通常 detail
- 单一聚合 + 按时间分桶（如"每天的 GMV"）→ trend，不是 metric

意图分类示例：
- "昨天的 GMV 是多少？"           → intent: metric
- "最近 7 天每日 GMV"            → intent: trend
- "本周 vs 上周 GMV 对比"         → intent: compare
- "昨天充值金额 Top 10 用户"      → intent: rank
- "用户按消费档次分布"            → intent: distribution
- "上周注册用户的 7 日留存"       → intent: retention
- "列出昨天注册的用户 ID"         → intent: detail

代词解析（强制规则）：用户用「这些」「上述」「刚才的」「他们」「那批」等指代词时：
1. 必须结合 history 中上一条 Q+SQL+结果定位到具体口径
2. is_clear=true，把口径完整写入 refined_question（如"列出 2026-04-25 注册的用户ID"）
3. 禁止以"上一题用的是聚合表/没有明细字段/数据库中是否存在 xx 表"为由追问 —— 这些是 sql_planner 的责任，不是澄清范围；找不到合适表由 sql_planner 报错
4. 数据源/表选择的疑虑写到 analysis_approach 里供下游参考，不要写到 clarification_question
5. 仅当 history 为空且代词无法从字面推断时才追问

正确示例：
  history Q: "2026-04-25 注册用户数" → SQL 用 ads_operation_report_daily.reg_user_num=8
  当前 Q: "把这些用户的ID列一下"
  正确输出：{"is_clear": true, "refined_question": "列出 2026-04-25 当天注册的用户的 ID", "analysis_approach": "上一题用的是聚合表无 ID，需 sql_planner 在 dwd/ods 层找用户注册明细表", "intent": "detail"}

Schema（表 / 字段 / 注释）：
{schema}

对话历史：
{history}"""


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
