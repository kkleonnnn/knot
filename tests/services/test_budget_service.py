"""tests/services/test_budget_service.py — v0.4.3 budget_service 单测（6 条）。

覆盖：
- R-16 优先级链：user 级覆盖 global 级
- R-19 趋势过滤 legacy（通过 service 调用）
- R-23 实时查（admin 改完立即生效；同 service 调两次拿不同结果）
- R-21 validate_budget_input 拒 legacy
- block 仅 agent_kind/per_call 允许
- agent per_call block 阻断逻辑
"""
import pytest

from knot.repositories import budget_repo, conversation_repo, message_repo, user_repo
from knot.services import budget_service


def _admin_id():
    return user_repo.get_user_by_username("admin")["id"]


def test_R16_user_budget_overrides_global(tmp_db_path):
    """user 有独立预算时忽略 global 预算（资深 R-16 优先级链）。"""
    uid = _admin_id()
    # 全局：5 USD 阈值
    budget_repo.upsert("global", "all", "monthly_cost_usd", 5.0, action="warn")
    # user：100 USD 阈值（更宽松）
    budget_repo.upsert("user", str(uid), "monthly_cost_usd", 100.0, action="warn")
    # 制造 user 累计 cost = 50（超 global 但未超 user）
    user_repo.update_user_usage(uid, 0, 0, 50.0, 0)

    status, meta = budget_service.check_user_monthly_budget(uid)
    # R-16: user 级生效；50 < 100 → ok（global 的 5 USD 被忽略）
    assert status == "ok", f"R-16 优先级失败：{status} / {meta}"


def test_R16_fallback_to_global_when_user_has_no_budget(tmp_db_path):
    """user 无独立预算 → fallback global（R-16 第二段）。"""
    uid = _admin_id()
    budget_repo.upsert("global", "all", "monthly_cost_usd", 5.0, action="warn")
    user_repo.update_user_usage(uid, 0, 0, 7.0, 0)

    status, meta = budget_service.check_user_monthly_budget(uid)
    assert status == "warn"
    assert meta["scope_type"] == "global"
    assert meta["threshold"] == 5.0
    assert meta["current"] == 7.0
    assert meta["percentage"] == 140.0


def test_R23_no_cache_admin_change_immediately_visible(tmp_db_path):
    """R-23 不缓存：admin 改预算后下次调用立即生效。"""
    uid = _admin_id()
    user_repo.update_user_usage(uid, 0, 0, 10.0, 0)

    # 首次：无预算 → ok
    status1, _ = budget_service.check_user_monthly_budget(uid)
    assert status1 == "ok"

    # admin 加预算（5 USD 阈值）
    budget_repo.upsert("global", "all", "monthly_cost_usd", 5.0, action="warn")

    # 立即下次调用 → warn（无 TTL 等待）
    status2, meta2 = budget_service.check_user_monthly_budget(uid)
    assert status2 == "warn"
    assert meta2["current"] == 10.0


def test_R21_validate_input_rejects_legacy_scope(tmp_db_path):
    """R-21：scope_type='agent_kind' AND scope_value='legacy' 一律拒。"""
    err = budget_service.validate_budget_input(
        "agent_kind", "legacy", "monthly_cost_usd", "warn",
    )
    assert err is not None
    assert "legacy" in err

    # 合法的 agent_kind 不被误杀
    err_ok = budget_service.validate_budget_input(
        "agent_kind", "fix_sql", "per_call_cost_usd", "block",
    )
    assert err_ok is None


def test_validate_block_only_for_agent_kind_per_call(tmp_db_path):
    """v0.4.3 范围：'block' 仅 agent_kind/per_call_cost_usd 允许；其他组合应拒。"""
    # user 级 block → 拒
    err = budget_service.validate_budget_input(
        "user", "1", "monthly_cost_usd", "block",
    )
    assert err is not None and "block" in err

    # global 级 block → 拒
    err2 = budget_service.validate_budget_input(
        "global", "all", "monthly_cost_usd", "block",
    )
    assert err2 is not None

    # agent_kind / monthly 级 block → 拒（必须配 per_call）
    err3 = budget_service.validate_budget_input(
        "agent_kind", "fix_sql", "monthly_cost_usd", "block",
    )
    assert err3 is not None


def test_check_agent_per_call_blocks_when_estimated_above_threshold(tmp_db_path):
    """agent_kind/per_call_cost_usd block 阻断 LLM 调用。"""
    budget_repo.upsert("agent_kind", "fix_sql", "per_call_cost_usd", 0.001, action="block")

    # 估算 cost 0.005 > 阈值 0.001 → 阻断
    allowed, meta = budget_service.check_agent_per_call_budget("fix_sql", 0.005)
    assert allowed is False
    assert meta["agent_kind"] == "fix_sql"
    assert meta["threshold"] == 0.001
    assert meta["estimated"] == 0.005

    # 估算 cost 0.0005 < 阈值 → 通过
    allowed2, _ = budget_service.check_agent_per_call_budget("fix_sql", 0.0005)
    assert allowed2 is True


def test_R19_recovery_trend_excludes_legacy(tmp_db_path):
    """R-19：legacy agent_kind 不参与趋势计算。"""
    uid = _admin_id()
    cid = conversation_repo.create_conversation(uid)

    # legacy 行（绕过 save_message 守护，直接 INSERT）
    from knot.repositories.base import get_conn
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (conversation_id, question, agent_kind, recovery_attempt) "
        "VALUES (?, ?, 'legacy', 99)",  # legacy 行 99 次自纠正应被过滤
        (cid, "old"),
    )
    conn.commit()
    conn.close()

    # 正常 sql_planner 行 2 次自纠正
    message_repo.save_message(
        cid, "Q", "SELECT 1", "ok", "high",
        [{"a": 1}], None, 0.001, 100, 50, 0,
        intent="metric", agent_kind="sql_planner", recovery_attempt=2,
    )

    trend = budget_service.get_recovery_trend(period_days=30)
    # R-19：legacy 99 不计入；只剩 sql_planner 的 2
    assert trend["total_recovery_attempts"] == 2, (
        f"R-19 过滤失败：legacy 行被计入趋势。trend={trend}"
    )
