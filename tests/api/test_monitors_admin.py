"""tests/api/test_monitors_admin.py — v0.7.7 C4 事件/规则/动作 admin 路由守护。

R-SL-65 gate + R-2FA carrier / CRUD + monitor.create/update/delete audit /
R-SL-77 check-now flag-gate（flag off 不 fire）/ check-now fire + monitor.trigger audit + 留痕（R-SL-75）。
"""
from knot.repositories import audit_repo, monitor_repo


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


def _mon_body(**kw):
    b = dict(name="gmv 异动", metric_name="gmv", comparator="lt", threshold=100.0,
             time_window="today", action_type="webhook", action_target="https://hooks.example.com/y")
    b.update(kw)
    return b


# ─── R-SL-65 gate + R-2FA carrier ────────────────────────────────────

def test_monitors_requires_auth(client):
    assert client.get("/api/admin/monitors").status_code in (401, 403)
    assert client.post("/api/admin/monitors/check-now").status_code in (401, 403)


def test_monitors_rejects_non_admin(client, auth_headers):
    client.post("/api/admin/users", json={"username": "mon_analyst", "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "mon_analyst", "password": "p"}).json()["token"]
    assert client.get("/api/admin/monitors", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_check_now_2fa_enroll_carrier(client, auth_headers, monkeypatch):
    """R-SL-65 R-2FA carrier：default-on + 未 enroll admin → 403 totp_enroll_required（仿 v0.7.2 R-SL-6）。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.post("/api/admin/monitors/check-now", headers=auth_headers)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_required"


# ─── CRUD + audit（R-SL-66）─────────────────────────────────────────

def test_crud_and_audit(client, auth_headers):
    cr = client.post("/api/admin/monitors", json=_mon_body(), headers=auth_headers)
    assert cr.status_code == 200
    mid = cr.json()["id"]
    assert _last_action("monitor.create") is not None
    assert len(client.get("/api/admin/monitors", headers=auth_headers).json()) == 1
    client.put(f"/api/admin/monitors/{mid}", json={"threshold": 50.0, "enabled": 0}, headers=auth_headers)
    assert _last_action("monitor.update") is not None
    assert monitor_repo.get_monitor(mid)["enabled"] == 0
    client.delete(f"/api/admin/monitors/{mid}", headers=auth_headers)
    assert _last_action("monitor.delete") is not None and monitor_repo.get_monitor(mid) is None


# ─── R-SL-77 check-now flag-gate（守护者聚焦）────────────────────────

def test_check_now_flag_gate_off_no_fire(client, auth_headers, monkeypatch):
    """R-SL-77：KNOT_SEMANTIC_LAYER off → check-now 不 fire（守零生产风险不变量）。"""
    monkeypatch.delenv("KNOT_SEMANTIC_LAYER", raising=False)
    client.post("/api/admin/monitors", json=_mon_body(), headers=auth_headers)
    r = client.post("/api/admin/monitors/check-now", headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is False and "语义层未启用" in r.json()["detail"]
    assert r.json()["results"] == []                          # 0 评估 0 fire


def test_check_now_fires_and_audits_and_logs(client, auth_headers, monkeypatch):
    """R-SL-77 flag on + 命中 → fire webhook + monitor.trigger audit + 留痕（R-SL-75 每 check 一行）。"""
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    cr = client.post("/api/admin/monitors", json=_mon_body(), headers=auth_headers)
    mid = cr.json()["id"]
    # mock engine（D3 非 None）+ eval 命中 + webhook send no-op（不真 POST）
    monkeypatch.setattr("knot.services.engine_cache.get_user_engine", lambda u: (object(), "schema"))
    from knot.services.semantic import monitor_eval
    monkeypatch.setattr(monitor_eval, "evaluate_monitor",
                        lambda *a: {"hit": True, "metric_value": 80.0, "status": "fired", "detail": "命中"})
    from knot.adapters.notification import webhook
    monkeypatch.setattr(webhook.WebhookNotificationAdapter, "send", lambda self, n: None)

    r = client.post("/api/admin/monitors/check-now", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["fired"] == 1 and body["results"][0]["status"] == "fired"
    assert _last_action("monitor.trigger") is not None        # R-SL-66 emit
    assert len(monitor_repo.list_triggers(mid)) == 1          # R-SL-75 留痕每 check 一行
