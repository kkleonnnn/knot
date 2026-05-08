"""budget_service — v0.4.3 预算检查 + System_Recovery 趋势。

8 条红线落点：
- R-16 优先级链：check_user_monthly_budget 先查 user 级，无则 fallback global
- R-17 一致性：cost 来源是 user_repo.monthly_cost_usd 缓存（不实时 SUM(messages)），
  v0.4.2 R-S8 已保证 user_repo 与 messages 累加值一致
- R-19 趋势过滤 legacy：调 message_repo.get_recovery_trend 已内含
- R-21 legacy 守护：API 层拒绝；service 也额外加防御
- R-23 不缓存：所有 budget_repo 调用都是实时（无 LRU / 模块 dict）
"""
from __future__ import annotations

from bi_agent.models.budget import V042_RELEASE_DATE
from bi_agent.repositories import budget_repo, message_repo, user_repo


def check_user_monthly_budget(user_id: int) -> tuple[str, dict | None]:
    """R-16：先查 scope=user/{user_id}；无独立预算则 fallback scope=global/all。
    R-17：current 从 user_repo.monthly_cost_usd 读（缓存，与 messages 一致 by R-S8）。
    R-23：每次实时查 budgets 表（admin 改完立即生效）。

    返 ('ok' | 'warn' | 'block', meta)。
    meta 形如 {budget_type, threshold, current, percentage}（仅 warn/block 时非空）。
    """
    # R-16 优先级 #1：user 级
    user_budgets = budget_repo.list_by_scope("user", str(user_id))
    if user_budgets:
        return _evaluate_monthly(user_budgets, user_id)

    # R-16 优先级 #2：global 级 fallback
    global_budgets = budget_repo.list_by_scope("global", "all")
    if global_budgets:
        return _evaluate_monthly(global_budgets, user_id)

    return "ok", None


def _evaluate_monthly(budgets: list[dict], user_id: int) -> tuple[str, dict | None]:
    """对 budgets 列表逐条评估月度类型；返第一个超阈值的（block 优先级 > warn）。"""
    # R-17：current 来源 user_repo（缓存）
    user = user_repo.get_user_by_id(user_id) or {}
    current_cost = float(user.get("monthly_cost_usd", 0) or 0)
    current_tokens = int(user.get("monthly_tokens", 0) or 0)

    # 收集所有月度类型违规
    block_hits: list[dict] = []
    warn_hits: list[dict] = []
    for b in budgets:
        bt = b["budget_type"]
        if bt == "monthly_cost_usd":
            current = current_cost
        elif bt == "monthly_tokens":
            current = float(current_tokens)
        else:
            continue  # per_call_cost_usd 不在月度评估中
        threshold = float(b["threshold"])
        if threshold <= 0 or current < threshold:
            continue
        meta = {
            "budget_type": bt,
            "threshold": threshold,
            "current": current,
            "percentage": round(current / threshold * 100, 1),
            "scope_type": b["scope_type"],
            "scope_value": b["scope_value"],
            "action": b["action"],
        }
        if b["action"] == "block":
            block_hits.append(meta)
        else:
            warn_hits.append(meta)

    # block 优先；同级取百分比最高
    if block_hits:
        return "block", max(block_hits, key=lambda m: m["percentage"])
    if warn_hits:
        return "warn", max(warn_hits, key=lambda m: m["percentage"])
    return "ok", None


def check_agent_per_call_budget(agent_kind: str, estimated_cost: float) -> tuple[bool, dict | None]:
    """R-23 实时查 agent_kind 级 per_call_cost_usd 预算；超阈值 block。

    返 (allowed, meta)；allowed=False 时 query.py 应在 LLM 调用前 raise BudgetExceeded
    或返回 error 给 client，避免 fix_sql 死循环烧钱。
    """
    if estimated_cost <= 0:
        return True, None
    budgets = budget_repo.list_by_scope("agent_kind", agent_kind)
    for b in budgets:
        if b["budget_type"] != "per_call_cost_usd" or b["action"] != "block":
            continue
        threshold = float(b["threshold"])
        if threshold > 0 and estimated_cost >= threshold:
            return False, {
                "budget_type": "per_call_cost_usd",
                "agent_kind": agent_kind,
                "threshold": threshold,
                "estimated": estimated_cost,
            }
    return True, None


def get_recovery_trend(period_days: int = 30) -> dict:
    """R-19 复用 message_repo.get_recovery_trend：过滤 legacy + v0.4.2 上线日起点。"""
    return message_repo.get_recovery_trend(period_days=period_days, since_date=V042_RELEASE_DATE)


# ── R-21 守护：service 层防御性检查（API 层主拦） ─────────────────────────────

def validate_budget_input(scope_type: str, scope_value: str,
                          budget_type: str, action: str) -> str | None:
    """返 None 表合法；返 error 字符串供 API 转 400 响应。

    R-21：scope_type='agent_kind' AND scope_value='legacy' 一律拒
    其他守护：'block' 仅允许 agent_kind/per_call_cost_usd 用（v0.4.3 范围）
    """
    from bi_agent.models.budget import (
        VALID_BUDGET_ACTIONS,
        VALID_BUDGET_SCOPES,
        VALID_BUDGET_TYPES,
    )
    if scope_type not in VALID_BUDGET_SCOPES:
        return f"非法 scope_type {scope_type!r}; 必须 ∈ {VALID_BUDGET_SCOPES}"
    if budget_type not in VALID_BUDGET_TYPES:
        return f"非法 budget_type {budget_type!r}; 必须 ∈ {VALID_BUDGET_TYPES}"
    if action not in VALID_BUDGET_ACTIONS:
        return f"非法 action {action!r}; 必须 ∈ {VALID_BUDGET_ACTIONS}"
    if scope_type == "agent_kind" and scope_value == "legacy":
        return "R-21: 'legacy' 是 v0.4.2 历史数据标记，不可设预算"
    if action == "block":
        # v0.4.3 范围：仅 agent_kind/per_call_cost_usd 允许 block
        if scope_type != "agent_kind" or budget_type != "per_call_cost_usd":
            return ("v0.4.3 范围内 'block' 仅允许配 (scope_type=agent_kind, "
                    "budget_type=per_call_cost_usd)；其他组合请用 'warn'")
    return None
