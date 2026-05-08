"""cost_service — v0.4.2 成本归因聚合服务。

职责（手册 §3.2）：
- 把分桶 agent_costs 累加为总 cost_usd / total_tokens（R-S8 唯一一致性入口）
- 按 agent_kind / period 聚合 admin 看板数据（C3 commit 用）
- 不调 LLM、不持久化（CRUD 由 message_repo / settings_repo 负责）

R-S8 不变量（守护者必修单测）：
    sum(agent_costs[*].cost) == cost_usd written to messages.cost_usd
                             == amount added to users.monthly_cost_usd
"""
from __future__ import annotations

from bi_agent.repositories import message_repo  # noqa: F401  reserved for breakdown query

# v0.4.2 agent kinds（与 models.agent.VALID_AGENT_KINDS 对齐，但 'legacy' 不参与新累加）
_NEW_AGENT_KINDS: tuple[str, ...] = ("clarifier", "sql_planner", "fix_sql", "presenter")


def empty_buckets() -> dict:
    """新建一个零值分桶 dict（key=agent_kind，value={cost, tokens}）。"""
    return {k: {"cost": 0.0, "tokens": 0} for k in _NEW_AGENT_KINDS}


def add_agent_cost(buckets: dict, agent_kind: str,
                   cost: float, input_tokens: int, output_tokens: int) -> None:
    """把单次 LLM 调用的开销累加到对应分桶。
    buckets 必须由 empty_buckets() 创建以保证 key 完整性。"""
    if agent_kind not in _NEW_AGENT_KINDS:
        raise ValueError(
            f"add_agent_cost: agent_kind={agent_kind!r} 不是有效新 agent_kind；"
            f"必须 ∈ {_NEW_AGENT_KINDS}"
        )
    buckets[agent_kind]["cost"] += float(cost or 0)
    buckets[agent_kind]["tokens"] += int(input_tokens or 0) + int(output_tokens or 0)


def aggregate_agent_costs(buckets: dict) -> tuple[float, int]:
    """把分桶 buckets 加和为 (total_cost_usd, total_tokens)。

    R-S8 唯一一致性入口：调用方拿到的 total_cost 必须直接写入 messages.cost_usd
    并通过 user_repo.update_user_usage 累加到 user.monthly_cost_usd，
    不允许在 query.py 里二次重算 total_cost（避免漂移）。
    """
    total_cost = 0.0
    total_tokens = 0
    for kind in _NEW_AGENT_KINDS:
        b = buckets.get(kind, {})
        total_cost += float(b.get("cost", 0) or 0)
        total_tokens += int(b.get("tokens", 0) or 0)
    return total_cost, total_tokens


def to_save_message_kwargs(buckets: dict) -> dict:
    """把分桶 dict 展开成 message_repo.save_message 的 cost_*/tokens_* 关键字参数。
    简化 query.py 调用（避免手敲 8 个参数）。"""
    return {
        "clarifier_cost":     buckets["clarifier"]["cost"],
        "sql_planner_cost":   buckets["sql_planner"]["cost"],
        "fix_sql_cost":       buckets["fix_sql"]["cost"],
        "presenter_cost":     buckets["presenter"]["cost"],
        "clarifier_tokens":   buckets["clarifier"]["tokens"],
        "sql_planner_tokens": buckets["sql_planner"]["tokens"],
        "fix_sql_tokens":     buckets["fix_sql"]["tokens"],
        "presenter_tokens":   buckets["presenter"]["tokens"],
    }


def to_sse_payload(buckets: dict) -> dict:
    """把分桶 dict 转成 SSE final 事件的 agent_costs 字段（前端消费）。
    R-S5 / Stage 3-B：不删 cost_usd 总和字段，agent_costs 是新增展开。"""
    return {kind: dict(buckets[kind]) for kind in _NEW_AGENT_KINDS}
