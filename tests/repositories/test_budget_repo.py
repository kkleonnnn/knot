"""tests/repositories/test_budget_repo.py — v0.4.3 budgets CRUD（4 条 + R-18 幂等）。"""
from bi_agent.repositories import budget_repo


def test_upsert_creates_new_row(tmp_db_path):
    rid = budget_repo.upsert("user", "1", "monthly_cost_usd", 5.0, action="warn")
    assert rid > 0
    b = budget_repo.get(rid)
    assert b["scope_type"] == "user"
    assert b["scope_value"] == "1"
    assert b["budget_type"] == "monthly_cost_usd"
    assert b["threshold"] == 5.0
    assert b["action"] == "warn"
    assert b["enabled"] == 1


def test_upsert_replaces_on_unique_conflict(tmp_db_path):
    """R-18 幂等：UNIQUE (scope_type, scope_value, budget_type) 冲突时
    INSERT OR REPLACE 应覆盖 threshold/action 而非抛 IntegrityError。"""
    rid1 = budget_repo.upsert("user", "1", "monthly_cost_usd", 5.0, action="warn")
    rid2 = budget_repo.upsert("user", "1", "monthly_cost_usd", 10.0, action="warn")
    # INSERT OR REPLACE 删旧再插新，rid 可能变化
    assert rid2 > 0
    # 同 UNIQUE 三元组只剩 1 条
    rows = budget_repo.list_all()
    matching = [b for b in rows if b["scope_type"] == "user" and b["scope_value"] == "1"
                and b["budget_type"] == "monthly_cost_usd"]
    assert len(matching) == 1
    assert matching[0]["threshold"] == 10.0  # 已被新值覆盖


def test_get_by_unique_returns_existing(tmp_db_path):
    """R-18 配套：service 层用此判断 already_existed。"""
    budget_repo.upsert("global", "all", "monthly_cost_usd", 100.0)
    found = budget_repo.get_by_unique("global", "all", "monthly_cost_usd")
    assert found is not None
    assert found["threshold"] == 100.0
    # 不存在 → None
    assert budget_repo.get_by_unique("user", "999", "monthly_cost_usd") is None


def test_list_by_scope_filters_enabled_only(tmp_db_path):
    """R-23 实时查 + enabled=0 不参与服务层评估。"""
    rid_on = budget_repo.upsert("agent_kind", "fix_sql", "per_call_cost_usd", 0.001)
    rid_off = budget_repo.upsert("agent_kind", "presenter", "monthly_cost_usd", 1.0)
    budget_repo.update(rid_off, enabled=0)

    active = budget_repo.list_by_scope("agent_kind", "fix_sql")
    assert len(active) == 1
    assert active[0]["id"] == rid_on

    disabled_scope = budget_repo.list_by_scope("agent_kind", "presenter")
    assert disabled_scope == []  # enabled=0 被过滤
