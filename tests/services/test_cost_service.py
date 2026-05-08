"""tests/services/test_cost_service.py — v0.4.2 成本归因服务单测。

覆盖：
- empty_buckets / add_agent_cost 加和正确
- aggregate_agent_costs 与 add_agent_cost 一致（R-S8 内部一致性）
- to_save_message_kwargs / to_sse_payload 字段映射正确
- agent_kind 守护：'legacy' 不允许写入 buckets
- R-S8 端到端一致性：buckets → save_message → users.monthly_cost_usd
"""
import pytest

from bi_agent.repositories import conversation_repo, message_repo, user_repo
from bi_agent.services import cost_service


def test_empty_buckets_has_4_kinds():
    b = cost_service.empty_buckets()
    assert set(b.keys()) == {"clarifier", "sql_planner", "fix_sql", "presenter"}
    for kind in b:
        assert b[kind] == {"cost": 0.0, "tokens": 0}


def test_add_agent_cost_accumulates():
    b = cost_service.empty_buckets()
    cost_service.add_agent_cost(b, "clarifier", 0.01, 100, 50)
    cost_service.add_agent_cost(b, "clarifier", 0.02, 200, 100)
    assert b["clarifier"]["cost"] == pytest.approx(0.03)
    assert b["clarifier"]["tokens"] == 450


def test_add_agent_cost_rejects_legacy():
    """Stage 3-A 守护：'legacy' 仅老消息持有，新累加禁止。"""
    b = cost_service.empty_buckets()
    with pytest.raises(ValueError, match="agent_kind"):
        cost_service.add_agent_cost(b, "legacy", 0.1, 10, 10)


def test_add_agent_cost_rejects_unknown_kind():
    b = cost_service.empty_buckets()
    with pytest.raises(ValueError):
        cost_service.add_agent_cost(b, "unknown_agent", 0.1, 10, 10)


def test_aggregate_equals_sum_of_buckets():
    """R-S8 唯一一致性入口：aggregate 必须等于手工求和。"""
    b = cost_service.empty_buckets()
    cost_service.add_agent_cost(b, "clarifier", 0.01, 100, 50)
    cost_service.add_agent_cost(b, "sql_planner", 0.05, 1000, 500)
    cost_service.add_agent_cost(b, "fix_sql", 0.02, 200, 100)
    cost_service.add_agent_cost(b, "presenter", 0.03, 500, 250)

    total_cost, total_tokens = cost_service.aggregate_agent_costs(b)
    assert total_cost == pytest.approx(0.01 + 0.05 + 0.02 + 0.03)
    assert total_tokens == (100 + 50) + (1000 + 500) + (200 + 100) + (500 + 250)


def test_to_save_message_kwargs_full_mapping():
    b = cost_service.empty_buckets()
    cost_service.add_agent_cost(b, "clarifier", 0.01, 100, 50)
    cost_service.add_agent_cost(b, "sql_planner", 0.05, 1000, 500)
    kw = cost_service.to_save_message_kwargs(b)
    assert kw["clarifier_cost"] == pytest.approx(0.01)
    assert kw["sql_planner_cost"] == pytest.approx(0.05)
    assert kw["fix_sql_cost"] == 0.0
    assert kw["clarifier_tokens"] == 150
    assert kw["sql_planner_tokens"] == 1500


def test_to_sse_payload_shape():
    """SSE final 事件 payload 是 {kind: {cost, tokens}} 的字典。"""
    b = cost_service.empty_buckets()
    cost_service.add_agent_cost(b, "presenter", 0.02, 300, 150)
    sse = cost_service.to_sse_payload(b)
    assert "presenter" in sse
    assert sse["presenter"]["cost"] == pytest.approx(0.02)
    assert sse["presenter"]["tokens"] == 450
    # 4 个 kind 都在
    assert set(sse.keys()) == {"clarifier", "sql_planner", "fix_sql", "presenter"}


# ── R-S8 端到端一致性（守护者必修） ──────────────────────────────────────────

def test_R_S8_end_to_end_cost_consistency(tmp_db_path):
    """R-S8 守护者必修：agent_costs 总和 == messages.cost_usd ==
    user.monthly_cost_usd 增量。三处累加值漂移会导致 admin 看板与计费失真。"""
    uid = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(uid)

    # 模拟三个 agent 的真实开销
    b = cost_service.empty_buckets()
    cost_service.add_agent_cost(b, "clarifier", 0.0011, 234, 100)
    cost_service.add_agent_cost(b, "sql_planner", 0.0050, 1234, 500)
    cost_service.add_agent_cost(b, "presenter", 0.0023, 456, 230)
    expected_total_cost, expected_total_tokens = cost_service.aggregate_agent_costs(b)

    # 1. save_message 用 aggregate 的结果作 cost_usd（R-S8 入口）
    mid = message_repo.save_message(
        cid, "Q", "SELECT 1", "ok", "high",
        [{"a": 1}], None,
        cost_usd=expected_total_cost,
        input_tokens=234 + 1234 + 456,
        output_tokens=100 + 500 + 230,
        retry_count=0,
        intent="metric",
        agent_kind="sql_planner",
        **cost_service.to_save_message_kwargs(b),
    )

    # 2. 拉回 message 验 cost_usd 一致
    msg = message_repo.get_message(mid)
    assert msg["cost_usd"] == pytest.approx(expected_total_cost)

    # 3. 验分桶字段也一致
    assert msg["clarifier_cost"] == pytest.approx(0.0011)
    assert msg["sql_planner_cost"] == pytest.approx(0.0050)
    assert msg["presenter_cost"] == pytest.approx(0.0023)
    assert msg["fix_sql_cost"] == 0.0
    # 分桶 cost 之和必须等于 cost_usd（R-S8 不变量）
    breakdown_sum = (msg["clarifier_cost"] + msg["sql_planner_cost"]
                     + msg["fix_sql_cost"] + msg["presenter_cost"])
    assert breakdown_sum == pytest.approx(msg["cost_usd"])

    # 4. 验 user.monthly_cost_usd 累加同款值
    user_repo.update_user_usage(uid, expected_total_tokens, 0, expected_total_cost, 0)
    u = user_repo.get_user_by_id(uid)
    assert u["monthly_cost_usd"] == pytest.approx(expected_total_cost)
