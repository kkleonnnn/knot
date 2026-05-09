"""tests/services/test_cost_alignment.py — v0.4.3 R-17 一致性对齐测试.

资深 Stage 2 R-17：高频路径 budget_service 从 user_repo.monthly_cost_usd 读 cost
（缓存值），不实时 SUM(messages)。必须保证两者一致（v0.4.2 R-S8 的延伸）。

模拟 100 次 add_agent_cost + save_message + update_user_usage 的真实闭环，
验证 user_repo.monthly_cost_usd 与 SUM(messages.cost_usd) 误差 ≤ 0.01%。
"""
import pytest

from knot.repositories import conversation_repo, message_repo, user_repo
from knot.repositories.base import get_conn
from knot.services import cost_service


def test_R17_user_repo_monthly_cost_aligns_with_messages_sum(tmp_db_path):
    """100 次模拟真实查询闭环后，user_repo.monthly_cost_usd 与 SUM(messages.cost_usd)
    误差 ≤ 0.01%（资深 R-17）。

    模拟流程（每次循环）：
    1. cost_service.empty_buckets() + add_agent_cost 三个 agent
    2. cost_service.aggregate_agent_costs() → total
    3. message_repo.save_message(... cost_usd=total ...)
    4. user_repo.update_user_usage(uid, ..., total, 0)

    验证：
    - sum(messages.cost_usd) == user.monthly_cost_usd
    - 误差比例 ≤ 0.0001 (0.01%)
    """
    uid = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(uid)

    expected_total_cost = 0.0
    expected_total_tokens = 0

    for i in range(100):
        b = cost_service.empty_buckets()
        # 每次累加一些零碎数字，浮点舍入风险高
        cost_service.add_agent_cost(b, "clarifier",   0.001 * (i % 7),  20 + i, 10 + (i % 3))
        cost_service.add_agent_cost(b, "sql_planner", 0.005 * (i % 11), 100 + i * 2, 50 + (i % 5))
        cost_service.add_agent_cost(b, "presenter",   0.002 * (i % 5),  30 + (i % 9), 15 + (i % 7))

        total_cost, total_tokens = cost_service.aggregate_agent_costs(b)

        message_repo.save_message(
            cid, f"Q{i}", "SELECT 1", "ok", "high",
            [{"a": 1}], None,
            cost_usd=total_cost,
            input_tokens=20 + 100 + 30 + i * 3,  # 与 b 中 in_tokens 求和粗略对齐
            output_tokens=10 + 50 + 15 + (i % 15),
            retry_count=0,
            intent="metric",
            agent_kind="sql_planner",
            **cost_service.to_save_message_kwargs(b),
        )

        # update_user_usage 用 aggregate 的 total_cost（R-S8 一致性入口）
        user_repo.update_user_usage(uid, total_tokens, 0, total_cost, 0)

        expected_total_cost += total_cost
        expected_total_tokens += total_tokens

    # 1. user_repo 累加值
    user = user_repo.get_user_by_id(uid)
    user_cost = float(user["monthly_cost_usd"] or 0)

    # 2. SUM(messages) 实时查
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM messages WHERE conversation_id=?",
        (cid,),
    ).fetchone()
    conn.close()
    msg_sum = float(row["total"] or 0)

    # R-17 验证：误差 ≤ 0.01%
    if expected_total_cost > 0:
        rel_err_user = abs(user_cost - expected_total_cost) / expected_total_cost
        rel_err_msg = abs(msg_sum - expected_total_cost) / expected_total_cost
        rel_err_two = abs(user_cost - msg_sum) / max(user_cost, msg_sum, 1e-9)
        assert rel_err_user < 0.0001, (
            f"user_repo 累加误差 {rel_err_user:.6%} > 0.01%；预期 {expected_total_cost}, 实际 {user_cost}"
        )
        assert rel_err_msg < 0.0001, (
            f"messages SUM 误差 {rel_err_msg:.6%} > 0.01%；预期 {expected_total_cost}, 实际 {msg_sum}"
        )
        assert rel_err_two < 0.0001, (
            f"R-17 user_repo vs SUM(messages) 漂移 {rel_err_two:.6%} > 0.01%；"
            f"user_cost={user_cost}, msg_sum={msg_sum}"
        )
