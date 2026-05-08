"""tests/api/test_budgets.py — v0.4.3 /api/admin/budgets 集成测试（4 条）。

R-18 幂等：重复 POST 同 UNIQUE → 200 + already_existed=True
R-21 守护：scope_type='agent_kind' AND scope_value='legacy' → 400
"""
from __future__ import annotations


def test_R18_idempotent_post_returns_already_existed_flag(client, auth_headers):
    """R-18 幂等：同 (scope_type, scope_value, budget_type) 三元组重复 POST →
    200 + already_existed=True；threshold 被覆盖。"""
    body = {
        "scope_type": "user", "scope_value": "1",
        "budget_type": "monthly_cost_usd", "threshold": 5.0, "action": "warn",
    }
    r1 = client.post("/api/admin/budgets", json=body, headers=auth_headers)
    assert r1.status_code == 200, r1.text
    assert r1.json()["already_existed"] is False
    assert r1.json()["threshold"] == 5.0

    body["threshold"] = 10.0
    r2 = client.post("/api/admin/budgets", json=body, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["already_existed"] is True
    assert r2.json()["threshold"] == 10.0  # 覆盖生效


def test_R21_post_rejects_agent_kind_legacy(client, auth_headers):
    """R-21 守护：legacy 是 v0.4.2 历史标记，不可设预算 → 400。"""
    r = client.post(
        "/api/admin/budgets",
        json={
            "scope_type": "agent_kind", "scope_value": "legacy",
            "budget_type": "monthly_cost_usd", "threshold": 1.0, "action": "warn",
        },
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "legacy" in r.json()["detail"]


def test_block_action_only_allowed_for_agent_kind_per_call(client, auth_headers):
    """v0.4.3 范围：'block' 仅允许 (agent_kind, per_call_cost_usd) 组合。"""
    # 错配：user 级 + block → 400
    r = client.post(
        "/api/admin/budgets",
        json={
            "scope_type": "user", "scope_value": "1",
            "budget_type": "monthly_cost_usd", "threshold": 5.0, "action": "block",
        },
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "block" in r.json()["detail"]

    # 正确：agent_kind/per_call/block → 200
    r2 = client.post(
        "/api/admin/budgets",
        json={
            "scope_type": "agent_kind", "scope_value": "fix_sql",
            "budget_type": "per_call_cost_usd", "threshold": 0.001, "action": "block",
        },
        headers=auth_headers,
    )
    assert r2.status_code == 200


def test_budgets_list_update_delete_round_trip(client, auth_headers):
    """list / put / delete 端到端。"""
    r = client.post(
        "/api/admin/budgets",
        json={
            "scope_type": "global", "scope_value": "all",
            "budget_type": "monthly_cost_usd", "threshold": 100.0, "action": "warn",
        },
        headers=auth_headers,
    )
    bid = r.json()["id"]

    listing = client.get("/api/admin/budgets", headers=auth_headers)
    assert listing.status_code == 200
    assert any(b["id"] == bid for b in listing.json())

    put = client.put(
        f"/api/admin/budgets/{bid}",
        json={"threshold": 200.0, "enabled": 0},
        headers=auth_headers,
    )
    assert put.status_code == 200
    assert put.json()["threshold"] == 200.0
    assert put.json()["enabled"] == 0

    d = client.delete(f"/api/admin/budgets/{bid}", headers=auth_headers)
    assert d.status_code == 200
    after = client.delete(f"/api/admin/budgets/{bid}", headers=auth_headers)
    assert after.status_code == 404
