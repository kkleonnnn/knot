"""tests/api/test_audit_list_route.py — v0.4.6 commit #3 admin GET 路由守护。

R-56 越权 / R-61 强制分页 / 筛选 / 时间窗口。
"""
from knot.repositories import audit_repo


def _seed(actor_id: int, action: str, resource_type: str = "user"):
    audit_repo.insert(
        actor_id=actor_id, actor_role="admin", actor_name="seed",
        action=action, resource_type=resource_type,
    )


# ─── R-56 越权防御 ───────────────────────────────────────────────────

def test_R56_analyst_cannot_view_audit_log(client, auth_headers):
    """analyst 拿不到 audit-log；403。"""
    # 创建 analyst
    client.post("/api/admin/users", headers=auth_headers, json={
        "username": "alice", "password": "pw", "role": "analyst",
    })
    # analyst 登录
    tok = client.post("/api/auth/login", json={"username": "alice", "password": "pw"}).json()["token"]
    r = client.get("/api/admin/audit-log", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_admin_can_list_audit(client, auth_headers):
    r = client.get("/api/admin/audit-log", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "limit" in body and "offset" in body


# ─── R-61 强制分页 ───────────────────────────────────────────────────

def test_R61_default_limit_50(client, auth_headers):
    r = client.get("/api/admin/audit-log", headers=auth_headers)
    assert r.json()["limit"] == 50


def test_R61_limit_capped_at_200(client, auth_headers):
    """?limit=10000 → 自动截至 200（不抛错，兼容前端误传）。"""
    r = client.get("/api/admin/audit-log?limit=10000", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["limit"] == 200


def test_R61_negative_limit_falls_to_default(client, auth_headers):
    r = client.get("/api/admin/audit-log?limit=-5", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["limit"] == 50


# ─── 筛选 ────────────────────────────────────────────────────────────

def test_filter_by_actor_id(client, auth_headers, tmp_db_path):
    # auth_headers 已触发若干条 audit；新加几条 actor_id=999 的
    _seed(999, "user.create")
    _seed(999, "user.update")
    r = client.get("/api/admin/audit-log?actor_id=999", headers=auth_headers)
    items = r.json()["items"]
    assert len(items) == 2
    assert all(i["actor_id"] == 999 for i in items)


def test_filter_by_action(client, auth_headers, tmp_db_path):
    _seed(1, "user.delete")
    r = client.get("/api/admin/audit-log?action=user.delete", headers=auth_headers)
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] == "user.delete"
