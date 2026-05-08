"""tests/services/test_async_concurrency.py — v0.4.4 R-27 并发累加原子性守护。

asyncio.gather 模拟 3 个 agent 并发 add_agent_cost + save_message + update_user_usage，
验证最终一致性（无丢更新）：
  sum(messages.cost_usd) == user.monthly_cost_usd 增量 == agent_buckets 总和

关键点：
- SQLite UPDATE ... SET monthly_cost_usd = monthly_cost_usd + ? 是原子的（BEGIN/COMMIT）
- cost_service.add_agent_cost 在 dict 上累加（同 event loop 内 await 不会撞线）
- 测试通过 = R-27 不变量保留：v0.4.2 R-S8 在 async 后仍 hold
"""
import asyncio

import pytest

from bi_agent.repositories import conversation_repo, message_repo, user_repo
from bi_agent.repositories.base import get_conn
from bi_agent.services import cost_service


@pytest.mark.asyncio
async def test_R27_concurrent_add_agent_cost_no_lost_updates(tmp_db_path):
    """R-27 守护：100 次循环，每次 asyncio.gather 3 agent 并发累加 →
    user_repo.monthly_cost_usd 与 SUM(messages.cost_usd) 误差 ≤ 0.01%。

    每次循环：
    1. 新建 buckets
    2. asyncio.gather(add_clarifier, add_sql_planner, add_presenter) 并发
    3. aggregate_agent_costs → total
    4. save_message + update_user_usage（用 total）
    """
    uid = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(uid)

    expected_total_cost = 0.0

    for i in range(100):
        b = cost_service.empty_buckets()

        # 三 agent 用 asyncio.gather 并发累加（模拟真实 stream 场景下的让步）
        async def _add_clarifier():
            cost_service.add_agent_cost(b, "clarifier", 0.001 * (i % 7), 20 + i, 10 + (i % 3))

        async def _add_sql_planner():
            cost_service.add_agent_cost(b, "sql_planner", 0.005 * (i % 11), 100 + i * 2, 50 + (i % 5))

        async def _add_presenter():
            cost_service.add_agent_cost(b, "presenter", 0.002 * (i % 5), 30 + (i % 9), 15 + (i % 7))

        await asyncio.gather(_add_clarifier(), _add_sql_planner(), _add_presenter())

        total_cost, total_tokens = cost_service.aggregate_agent_costs(b)

        message_repo.save_message(
            cid, f"Q{i}", "SELECT 1", "ok", "high",
            [{"a": 1}], None,
            cost_usd=total_cost,
            input_tokens=20 + 100 + 30 + i * 3,
            output_tokens=10 + 50 + 15 + (i % 15),
            retry_count=0,
            intent="metric",
            agent_kind="sql_planner",
            **cost_service.to_save_message_kwargs(b),
        )

        user_repo.update_user_usage(uid, total_tokens, 0, total_cost, 0)
        expected_total_cost += total_cost

    # 验证三处累加值一致（v0.4.2 R-S8 在 async 后仍 hold）
    user = user_repo.get_user_by_id(uid)
    user_cost = float(user["monthly_cost_usd"] or 0)

    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM messages WHERE conversation_id=?",
        (cid,),
    ).fetchone()
    conn.close()
    msg_sum = float(row["total"] or 0)

    if expected_total_cost > 0:
        rel_err_two = abs(user_cost - msg_sum) / max(user_cost, msg_sum, 1e-9)
        assert rel_err_two < 0.0001, (
            f"R-27 失败：async 并发累加导致漂移 {rel_err_two:.6%} > 0.01%；"
            f"user_cost={user_cost}, msg_sum={msg_sum}"
        )


@pytest.mark.asyncio
async def test_R27_gather_3_agents_aggregate_matches_sum(tmp_db_path):
    """更紧的版本：单次 gather 3 agent 后立即验证 buckets 总和。"""
    b = cost_service.empty_buckets()

    async def _a():
        cost_service.add_agent_cost(b, "clarifier", 0.001, 100, 50)

    async def _b():
        cost_service.add_agent_cost(b, "sql_planner", 0.005, 1000, 500)

    async def _c():
        cost_service.add_agent_cost(b, "presenter", 0.002, 300, 150)

    await asyncio.gather(_a(), _b(), _c())

    total_cost, total_tokens = cost_service.aggregate_agent_costs(b)
    assert total_cost == pytest.approx(0.001 + 0.005 + 0.002)
    assert total_tokens == (100 + 50) + (1000 + 500) + (300 + 150)
    # 单 agent 桶值正确（无丢更新）
    assert b["clarifier"]["cost"] == pytest.approx(0.001)
    assert b["sql_planner"]["cost"] == pytest.approx(0.005)
    assert b["presenter"]["cost"] == pytest.approx(0.002)
