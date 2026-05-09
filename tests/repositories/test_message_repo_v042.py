"""tests/repositories/test_message_repo_v042.py — v0.4.2 agent_kind 守护 + 老消息回填。

覆盖 Stage 3-A 守护：
- save_message 显式传 'legacy' → ValueError
- save_message 传未知 agent_kind → ValueError
- 默认 'sql_planner' 通过
- init_db 后所有老消息 agent_kind='legacy'（DEFAULT 兜底 + UPDATE 保险）
- 新消息成本分桶字段持久化正确
"""
import pytest

from knot.repositories import conversation_repo, message_repo, user_repo


def _admin_id():
    return user_repo.get_user_by_username("admin")["id"]


def test_save_message_default_agent_kind_is_sql_planner(tmp_db_path):
    """默认 agent_kind=sql_planner 通过守护（v0.4.0+ 主路径）。"""
    cid = conversation_repo.create_conversation(_admin_id())
    mid = message_repo.save_message(cid, "Q", "SELECT 1", "ok", "high",
                                     [{"a": 1}], None, 0.01, 10, 5, 0)
    msg = message_repo.get_message(mid)
    assert msg["agent_kind"] == "sql_planner"


def test_save_message_rejects_legacy_agent_kind(tmp_db_path):
    """Stage 3-A 不变量：'legacy' 仅供老消息持有，新写入禁止。"""
    cid = conversation_repo.create_conversation(_admin_id())
    with pytest.raises(ValueError, match="legacy"):
        message_repo.save_message(cid, "Q", "SELECT 1", "ok", "high",
                                   [{"a": 1}], None, 0.01, 10, 5, 0,
                                   agent_kind="legacy")


def test_save_message_rejects_unknown_agent_kind(tmp_db_path):
    cid = conversation_repo.create_conversation(_admin_id())
    with pytest.raises(ValueError, match="Invalid agent_kind"):
        message_repo.save_message(cid, "Q", "SELECT 1", "ok", "high",
                                   [{"a": 1}], None, 0.01, 10, 5, 0,
                                   agent_kind="bogus_agent")


def test_save_message_cost_breakdown_persisted(tmp_db_path):
    """v0.4.2 成本归因字段 round-trip。"""
    cid = conversation_repo.create_conversation(_admin_id())
    mid = message_repo.save_message(
        cid, "Q", "SELECT 1", "ok", "high",
        [{"a": 1}], None, 0.05, 100, 50, 0,
        agent_kind="sql_planner",
        clarifier_cost=0.01, sql_planner_cost=0.03, fix_sql_cost=0.0, presenter_cost=0.01,
        clarifier_tokens=20, sql_planner_tokens=80, fix_sql_tokens=0, presenter_tokens=50,
        recovery_attempt=2,
    )
    msg = message_repo.get_message(mid)
    assert msg["clarifier_cost"] == 0.01
    assert msg["sql_planner_cost"] == 0.03
    assert msg["fix_sql_cost"] == 0.0
    assert msg["presenter_cost"] == 0.01
    assert msg["clarifier_tokens"] == 20
    assert msg["sql_planner_tokens"] == 80
    assert msg["recovery_attempt"] == 2


def test_init_db_backfills_legacy_for_old_messages(tmp_db_path):
    """R-S6 / Stage 3-A 保险：所有老消息 agent_kind='legacy'。
    本测试在 fresh DB 上跑（init_db 已执行），不会有老消息；
    但验证 schema DEFAULT 'legacy' 确实生效。"""
    from knot.repositories.base import get_conn
    conn = get_conn()
    # 直接 INSERT 不走 save_message（模拟 v0.4.2 之前的写入）
    cid = conversation_repo.create_conversation(_admin_id())
    conn.execute(
        "INSERT INTO messages (conversation_id, question) VALUES (?, ?)",
        (cid, "fake-old"),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT agent_kind FROM messages WHERE question='fake-old'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["agent_kind"] == "legacy"  # DEFAULT 'legacy' 兜底


def test_agent_kind_literal_includes_fix_sql():
    """资深 Stage 4 拍板：fix_sql 是独立 agent_kind 不是 sql_planner.retry。"""
    from knot.models.agent import VALID_AGENT_KINDS
    assert "fix_sql" in VALID_AGENT_KINDS
    assert "clarifier" in VALID_AGENT_KINDS
    assert "sql_planner" in VALID_AGENT_KINDS
    assert "presenter" in VALID_AGENT_KINDS
    assert "legacy" in VALID_AGENT_KINDS
    assert len(VALID_AGENT_KINDS) == 5
