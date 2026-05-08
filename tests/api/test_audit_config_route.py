"""tests/api/test_audit_config_route.py — v0.4.6 commit #5 retention config 路由守护。

R-49 retention 7~3650 区间 + R-57 meta-audit + R-56 越权防御
"""
from bi_agent.repositories import audit_repo


def _last_action(prefix: str):
    rows = audit_repo.list_filtered(page=1, size=200)
    for r in rows:
        if r["action"].startswith(prefix):
            return r
    return None


def test_R49_get_audit_config_default_90(client, auth_headers):
    r = client.get("/api/admin/audit-config", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["retention_days"] == 90


def test_R49_admin_can_update_retention(client, auth_headers):
    r = client.put("/api/admin/audit-config", headers=auth_headers,
                   json={"retention_days": 180})
    assert r.status_code == 200
    r2 = client.get("/api/admin/audit-config", headers=auth_headers)
    assert r2.json()["retention_days"] == 180


def test_R49_retention_below_7_rejected(client, auth_headers):
    r = client.put("/api/admin/audit-config", headers=auth_headers,
                   json={"retention_days": 3})
    assert r.status_code == 400


def test_R49_retention_above_3650_rejected(client, auth_headers):
    r = client.put("/api/admin/audit-config", headers=auth_headers,
                   json={"retention_days": 5000})
    assert r.status_code == 400


def test_R57_retention_change_meta_audit(client, auth_headers):
    """R-57：retention 调整本身入 audit_log（action='audit.retention_change'）。"""
    client.put("/api/admin/audit-config", headers=auth_headers,
               json={"retention_days": 120})
    rec = _last_action("audit.retention_change")
    assert rec is not None
    assert rec["detail_json"].get("new") == 120


def test_R56_analyst_cannot_modify_retention(client, auth_headers):
    """R-56 越权防御：analyst PUT 必 403。"""
    client.post("/api/admin/users", headers=auth_headers, json={
        "username": "alice2", "password": "pw", "role": "analyst"})
    tok = client.post("/api/auth/login",
                      json={"username": "alice2", "password": "pw"}).json()["token"]
    r = client.put("/api/admin/audit-config",
                   headers={"Authorization": f"Bearer {tok}"},
                   json={"retention_days": 200})
    assert r.status_code == 403
