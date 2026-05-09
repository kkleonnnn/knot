"""tests/api/test_audit_integration.py — v0.4.6 commit #3 集成测试。

8 类 mutation 各覆盖 1 条以上 audit 落点（R-63 完整 + messages 显式排除）。
"""
from __future__ import annotations

from typing import Optional

import pytest

from knot.repositories import audit_repo


def _last_action(action_prefix: str) -> Optional[dict]:
    rows = audit_repo.list_filtered(page=1, size=200)
    for r in rows:
        if r["action"].startswith(action_prefix):
            return r
    return None


# ─── auth ────────────────────────────────────────────────────────────

def test_audit_login_success(client, auth_headers):
    """登录成功（auth_headers fixture 已触发一次 login）→ audit 见 auth.login_success。"""
    r = _last_action("auth.login_success")
    assert r is not None
    assert r["actor_name"] == "admin"
    # R-58 client_ip / user_agent 列必有值（TestClient 默认 testclient）
    assert r["client_ip"] is not None


def test_audit_login_fail_records_attempted_username(client):
    """D5：失败登录 actor=None；detail 含 attempted_username。"""
    client.post("/api/auth/login", json={"username": "ghost-user", "password": "wrong"})
    r = _last_action("auth.login_fail")
    assert r is not None
    assert r["actor_id"] is None
    assert r["detail_json"].get("attempted_username") == "ghost-user"
    assert r["success"] == 0


# ─── users ───────────────────────────────────────────────────────────

def test_audit_user_create_and_disable(client, auth_headers):
    r = client.post("/api/admin/users", headers=auth_headers, json={
        "username": "alice", "password": "pw", "role": "analyst",
    })
    assert r.status_code == 200
    rec = _last_action("user.create")
    assert rec is not None
    assert rec["detail_json"].get("username") == "alice"
    # PII 不入 detail
    assert rec["detail_json"].get("password") in (None, "••••redacted••••")

    uid = r.json()["id"]
    r2 = client.delete(f"/api/admin/users/{uid}", headers=auth_headers)
    assert r2.status_code == 200
    rec2 = _last_action("user.disable")
    assert rec2["resource_id"] == str(uid)


def test_audit_user_role_change(client, auth_headers):
    r = client.post("/api/admin/users", headers=auth_headers,
                    json={"username": "bob", "password": "p", "role": "analyst"})
    uid = r.json()["id"]
    client.put(f"/api/admin/users/{uid}", headers=auth_headers, json={"role": "admin"})
    rec = _last_action("user.role_change")
    assert rec is not None
    assert rec["detail_json"].get("new_role") == "admin"


# ─── datasources ─────────────────────────────────────────────────────

def test_audit_datasource_create(client, auth_headers):
    client.post("/api/admin/datasources", headers=auth_headers, json={
        "name": "ds1", "db_host": "h", "db_user": "u", "db_password": "secret",
        "db_database": "db",
    })
    rec = _last_action("datasource.create")
    assert rec is not None
    # R-48：db_password 不入 detail（即使集成路由 detail 没传，守 helper 风格）
    assert "secret" not in str(rec["detail_json"])


# ─── api keys ────────────────────────────────────────────────────────

def test_audit_api_key_set_global_no_plaintext(client, auth_headers):
    client.put("/api/admin/api-keys", headers=auth_headers,
               json={"openrouter_api_key": "sk-or-real-secret-9999"})
    rec = _last_action("api_key.set_global")
    assert rec is not None
    # R-48 + R-59：detail 只记 keys 名单，不记任何 value（明文/密文都不入）
    assert "sk-or-real-secret" not in str(rec["detail_json"])
    assert "enc_v1:" not in str(rec["detail_json"])


# ─── budgets ─────────────────────────────────────────────────────────

def test_audit_budget_create(client, auth_headers):
    r = client.post("/api/admin/budgets", headers=auth_headers, json={
        "scope_type": "global", "scope_value": "all",
        "budget_type": "monthly_cost_usd", "threshold": 100.0,
        "action": "warn", "enabled": 1,
    })
    assert r.status_code == 200, r.text
    rec = _last_action("budget.")
    assert rec is not None
    assert rec["action"] in ("budget.create", "budget.update")


# ─── agent-models config ────────────────────────────────────────────

def test_audit_agent_models_update(client, auth_headers):
    client.put("/api/admin/agent-models", headers=auth_headers, json={
        "clarifier": "claude-haiku-4-5-20251001",
        "sql_planner": "claude-haiku-4-5-20251001",
        "presenter": "claude-haiku-4-5-20251001",
    })
    rec = _last_action("config.agent_models_update")
    assert rec is not None


# ─── prompts / few_shots / catalog config ───────────────────────────

def test_audit_prompt_update(client, auth_headers):
    client.put("/api/prompts/clarifier", headers=auth_headers, json={"content": "你是 X"})
    rec = _last_action("config.prompt_update")
    assert rec is not None
    assert rec["resource_id"] == "clarifier"


def test_audit_few_shots_create(client, auth_headers):
    client.post("/api/few-shots", headers=auth_headers, json={
        "question": "Q?", "sql": "SELECT 1", "type": "trend", "is_active": 1,
    })
    rec = _last_action("config.few_shots_change")
    assert rec is not None
    assert rec["detail_json"].get("op") == "create"


def test_audit_catalog_update(client, auth_headers):
    client.put("/api/admin/catalog", headers=auth_headers, json={"business_rules": "rule X"})
    rec = _last_action("config.catalog_update")
    assert rec is not None


# ─── R-63 messages 显式不入审计 ─────────────────────────────────────

def test_R63_messages_routes_do_not_call_audit():
    """grep 守护：query.py / conversations.py 不应 import audit_helpers / audit_service。"""
    from pathlib import Path
    forbidden = ["knot/api/query.py", "knot/api/conversations.py"]
    for f in forbidden:
        src = Path(f).read_text()
        assert "audit_service" not in src and "_audit_helpers" not in src, \
            f"R-63：{f} 不应调审计（messages 表已覆盖）"


# ─── R-47 fail-soft 端到端 ──────────────────────────────────────────

def test_R47_audit_repo_failure_does_not_break_route(client, auth_headers, monkeypatch):
    """mock audit_repo.insert 抛错 → 业务路由仍 200。"""
    from knot.repositories import audit_repo as ar
    monkeypatch.setattr(ar, "insert", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    r = client.post("/api/admin/users", headers=auth_headers, json={
        "username": "fail-safe", "password": "pw", "role": "analyst",
    })
    assert r.status_code == 200, "R-47：audit 失败不应阻断业务"
