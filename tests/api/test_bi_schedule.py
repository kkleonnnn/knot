"""tests/api/test_bi_schedule.py — v0.8.17 ②c 调度端点：tick token 门 + schedule CRUD 权限 + fires。"""


def _make_report(client, auth_headers):
    return client.post("/api/bi/reports", json={"title": "日报", "sql_text": "SELECT 1 AS a"},
                       headers=auth_headers).json()["id"]


def _analyst_headers(client, auth_headers, uname="sched_analyst"):
    client.post("/api/admin/users", json={"username": uname, "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": uname, "password": "p"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_tick_no_token_503(client, monkeypatch):
    """未配 KNOT_SCHEDULER_TOKEN → 调度端点 disabled（安全默认）。"""
    monkeypatch.delenv("KNOT_SCHEDULER_TOKEN", raising=False)
    assert client.post("/api/bi/scheduler/tick").status_code == 503


def test_tick_wrong_token_401(client, monkeypatch):
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    assert client.post("/api/bi/scheduler/tick",
                       headers={"Authorization": "Bearer nope"}).status_code == 401


def test_tick_correct_token_runs(client, monkeypatch):
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    r = client.post("/api/bi/scheduler/tick", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 200 and "checked" in r.json() and "fired" in r.json()


def test_schedule_crud_admin(client, auth_headers):
    rid = _make_report(client, auth_headers)
    r = client.put(f"/api/bi/reports/{rid}/schedule",
                   json={"enabled": True, "cadence": "daily", "run_at_hhmm": "08:00"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["cadence"] == "daily" and r.json()["next_run_at"]
    g = client.get(f"/api/bi/reports/{rid}/schedule", headers=auth_headers).json()
    assert g["enabled"] == 1 and g["run_at_hhmm"] == "08:00"
    # 停用 → next_run 清空（list_due 不再取）
    client.put(f"/api/bi/reports/{rid}/schedule", json={"enabled": False, "cadence": "daily"}, headers=auth_headers)
    assert client.get(f"/api/bi/reports/{rid}/schedule", headers=auth_headers).json()["next_run_at"] is None
    # 删
    assert client.delete(f"/api/bi/reports/{rid}/schedule", headers=auth_headers).status_code == 200
    assert client.get(f"/api/bi/reports/{rid}/schedule", headers=auth_headers).json() is None


def test_schedule_bad_cadence_400(client, auth_headers):
    rid = _make_report(client, auth_headers)
    assert client.put(f"/api/bi/reports/{rid}/schedule",
                      json={"cadence": "weekly"}, headers=auth_headers).status_code == 400


def test_schedule_every_n_hours_requires_interval_400(client, auth_headers):
    rid = _make_report(client, auth_headers)
    assert client.put(f"/api/bi/reports/{rid}/schedule",
                      json={"cadence": "every_n_hours"}, headers=auth_headers).status_code == 400


def test_schedule_analyst_no_grant_403(client, auth_headers):
    rid = _make_report(client, auth_headers)
    ah = _analyst_headers(client, auth_headers)
    assert client.put(f"/api/bi/reports/{rid}/schedule",
                      json={"cadence": "daily"}, headers=ah).status_code == 403
    assert client.get(f"/api/bi/reports/{rid}/schedule", headers=ah).status_code == 403


def test_schedule_fires_endpoint(client, auth_headers):
    rid = _make_report(client, auth_headers)
    assert client.get(f"/api/bi/reports/{rid}/schedule/fires", headers=auth_headers).json() == []
