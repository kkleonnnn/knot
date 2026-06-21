"""knot/api/admin/stats.py — admin 看板/指标聚合路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from knot.api.deps import require_admin
from knot.repositories import settings_repo
from knot.services import budget_service, cost_service

router = APIRouter()


# ── Cost Stats (v0.4.2 admin 看板) ─────────────────────────────────────

@router.get("/api/admin/cost-stats")
async def admin_cost_stats(period: str = "7d", admin=Depends(require_admin)):
    """v0.4.2 成本归因汇总（按 agent_kind 分桶 + 按 user 分组）。

    Query params:
      - period: 时段 ('7d' / '30d' / '90d' 或裸数字天)，默认 7d

    返回（详见 message_repo.get_cost_breakdown）：
      {period_days, total_cost_usd, total_messages,
       by_agent_kind: {clarifier, sql_planner, fix_sql, presenter, legacy},
       by_user: [...], recovery_attempt_total}
    """
    return cost_service.get_cost_breakdown_by_period(period)


# ── System Recovery 趋势（v0.4.3 R-19）──────────────────────────────────

@router.get("/api/admin/recovery-stats")
async def admin_recovery_stats(period: str = "30d", admin=Depends(require_admin)):
    """v0.4.3 自纠正趋势（R-19 过滤 legacy + v0.4.2 上线日起点）。

    Query params:
      - period: '7d' / '30d' / '90d' 或裸数字天，默认 30d

    返回（详见 message_repo.get_recovery_trend）：
      {period_days, total_recovery_attempts, total_messages,
       by_day: [{date, count, msg_count}, ...],
       top_users: [{user_id, username, count, msg_count}, ...]}
    """
    days = 30
    s = (period or "").strip().lower()
    if s.endswith("d") and s[:-1].isdigit():
        days = max(1, int(s[:-1]))
    elif s.isdigit():
        days = max(1, int(s))
    return budget_service.get_recovery_trend(period_days=days)


# ─── v0.5.40 后端真数据 stats endpoints ──────────────────────────────────

@router.get("/api/admin/metrics")
async def admin_internal_metrics(period: str = "7d", admin=Depends(require_admin)):
    """v0.6.1.0 — 内测健康指标：一次成功率 / 澄清率 / P95 latency / cost。

    Query params:
      - period: '7d' / '30d' / '90d' 或裸数字天，默认 7d（内测期主要观察短窗口）

    返回：
      {
        period_days: int,
        total_messages: int,                  # 期内所有非 legacy 消息
        first_try_success: {
          rate: float (0~1),                  # presenter & recovery_attempt=0 占所有 presenter 的比例
          numerator: int, denominator: int,
        },
        clarification: {
          rate: float (0~1),                  # clarifier 消息占总消息的比例
          numerator: int, denominator: int,
        },
        latency_ms: {
          p50: int | None, p95: int | None, p99: int | None,
          sample_size: int,                   # 有 latency_ms 数据的消息数
        },
        cost_usd: {
          total: float,                       # 期内总成本
          avg_per_message: float,             # 平均每消息成本
        },
      }
    """
    from knot.repositories import get_conn

    days = 7
    s = (period or "").strip().lower()
    if s.endswith("d") and s[:-1].isdigit():
        days = max(1, int(s[:-1]))
    elif s.isdigit():
        days = max(1, int(s))

    conn = get_conn()
    # 期窗：created_at >= datetime('now', '-Nd', 'localtime')
    cutoff_clause = f"datetime('now', '-{days} days', 'localtime')"

    # 1. 总消息数（排除 legacy 老消息 — 与 recovery-stats R-19 同口径）
    total = conn.execute(
        f"SELECT COUNT(*) FROM messages WHERE agent_kind != 'legacy' "
        f"AND created_at >= {cutoff_clause}"
    ).fetchone()[0] or 0

    # 2. 一次成功率：presenter 输出（最终成功路径）+ recovery_attempt=0
    success_num = conn.execute(
        f"SELECT COUNT(*) FROM messages "
        f"WHERE agent_kind = 'sql_planner' AND recovery_attempt = 0 "
        f"AND created_at >= {cutoff_clause}"
    ).fetchone()[0] or 0
    success_den = conn.execute(
        f"SELECT COUNT(*) FROM messages WHERE agent_kind = 'sql_planner' "
        f"AND created_at >= {cutoff_clause}"
    ).fetchone()[0] or 0

    # 3. 澄清率：clarifier 终态 / 期内所有消息
    clarif_num = conn.execute(
        f"SELECT COUNT(*) FROM messages WHERE agent_kind = 'clarifier' "
        f"AND created_at >= {cutoff_clause}"
    ).fetchone()[0] or 0

    # 4. P50/P95/P99 latency — Python 侧排序（内测期数据量小；DAU 5-20，< 10k/period）
    latencies = [
        row[0] for row in conn.execute(
            f"SELECT latency_ms FROM messages "
            f"WHERE latency_ms IS NOT NULL AND agent_kind != 'legacy' "
            f"AND created_at >= {cutoff_clause} ORDER BY latency_ms"
        ).fetchall()
    ]
    p50 = p95 = p99 = None
    if latencies:
        n = len(latencies)
        p50 = latencies[min(n - 1, int(n * 0.50))]
        p95 = latencies[min(n - 1, int(n * 0.95))]
        p99 = latencies[min(n - 1, int(n * 0.99))]

    # 5. 总成本（cost_usd 已是聚合值；agent_kind != legacy 避免老消息混入）
    cost_row = conn.execute(
        f"SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM messages "
        f"WHERE agent_kind != 'legacy' AND created_at >= {cutoff_clause}"
    ).fetchone()
    conn.close()
    total_cost = float(cost_row[0] or 0)
    cost_count = int(cost_row[1] or 0)

    return {
        "period_days": days,
        "total_messages": total,
        "first_try_success": {
            "rate": (success_num / success_den) if success_den else 0.0,
            "numerator": success_num,
            "denominator": success_den,
        },
        "clarification": {
            "rate": (clarif_num / total) if total else 0.0,
            "numerator": clarif_num,
            "denominator": total,
        },
        "latency_ms": {
            "p50": p50, "p95": p95, "p99": p99,
            "sample_size": len(latencies),
        },
        "cost_usd": {
            "total": round(total_cost, 4),
            "avg_per_message": round(total_cost / cost_count, 4) if cost_count else 0.0,
        },
    }


@router.get("/api/admin/query-history")
async def admin_query_history(
    period: str = "7d",
    user_id: int | None = None,
    agent_kind: str | None = None,
    has_error: bool | None = None,
    page: int = 1,
    size: int = 50,
    admin=Depends(require_admin),
):
    """v0.6.0.18 — admin 用户查询历史屏数据源（脱敏链 2/3）。

    全部用户的消息聚合（跨 conversation）；admin 全字段（含 sql_text）；
    支持按 user_id / period / agent_kind / has_error 过滤。

    Query params:
      - period: '7d' / '30d' / '90d' 或裸数字天，默认 7d
      - user_id: 仅看某用户（None=所有）
      - agent_kind: clarifier / sql_planner / fix_sql / presenter（None=所有）
      - has_error: true=只看错误 / false=只看成功 / None=所有
      - page / size: 分页（size 上限 200，默认 50）

    返回：{items: [...], total: int, page: int, size: int}
    """
    from knot.repositories import message_repo

    days = 7
    s = (period or "").strip().lower()
    if s.endswith("d") and s[:-1].isdigit():
        days = max(1, int(s[:-1]))
    elif s.isdigit():
        days = max(1, int(s))

    return message_repo.list_messages_for_admin(
        period_days=days,
        user_id=user_id,
        agent_kind=agent_kind,
        has_error=has_error,
        page=page,
        size=size,
    )


@router.get("/api/admin/audit-stats")
async def admin_audit_stats(admin=Depends(require_admin)):
    """v0.5.40 — 审计日志聚合 stats（总记录数/今日/失败数/涉及用户）。"""
    from knot.repositories import get_conn
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) AS today,
          SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed,
          COUNT(DISTINCT actor_id) AS distinct_users
        FROM audit_log
        """
    ).fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "today": row[1] or 0,
        "failed": row[2] or 0,
        "distinct_users": row[3] or 0,
    }


@router.get("/api/admin/budgets-stats")
async def admin_budgets_stats(admin=Depends(require_admin)):
    """v0.5.40 — 预算 Hero card 聚合 stats（本月已用 token / 预计花费 / 使用率）。

    本月已用 token: SUM(input_tokens + output_tokens) 当月 messages
    预计花费: SUM(cost_usd) 当月 messages
    使用率: 若有 global monthly_tokens budget 配置 → tokens_used / threshold
    """
    from knot.repositories import get_conn
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens_used,
          COALESCE(SUM(cost_usd), 0) AS cost_usd
        FROM messages
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')
        """
    ).fetchone()
    tokens_used = row[0] or 0
    cost_usd = row[1] or 0.0
    conn.close()
    # v0.5.42 — 使用率 from app_settings budget_monthly_token_cap（demo 单 global config 模式）
    try:
        cap = int(settings_repo.get_app_setting("budget_monthly_token_cap", "500000"))
    except (ValueError, TypeError):
        cap = None
    usage_pct = (tokens_used / cap * 100) if (cap and cap > 0) else None
    return {
        "tokens_used": tokens_used,
        "cost_usd": round(cost_usd, 4),
        "usage_pct": round(usage_pct, 1) if usage_pct is not None else None,
        "cap": cap,
    }
