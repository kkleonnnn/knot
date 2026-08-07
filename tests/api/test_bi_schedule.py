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
    assert client.post("/api/bi/scheduler/tick?tenant=default").status_code == 503


def test_tick_wrong_token_401(client, monkeypatch):
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    assert client.post("/api/bi/scheduler/tick?tenant=default",
                       headers={"Authorization": "Bearer nope"}).status_code == 401


def test_tick_correct_token_runs(client, monkeypatch):
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    r = client.post("/api/bi/scheduler/tick?tenant=default", headers={"Authorization": "Bearer secret123"})
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


# ─── v0.9.17：tick 租户域化（`tenant` 必填 · 自建 ctx）───────────────────────

def test_tick_without_tenant_is_refused(client, monkeypatch):
    """守什么：缺 `tenant` ⇒ **拒绝执行**（破坏性动作不得有默认目标；tick 会写=刷新报表）。

    取材：把 `tenant: str` 改成 `tenant: str | None = None` + 回退 `resolve_single_tenant()` ⇒ 本测红。
    """
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    r = client.post("/api/bi/scheduler/tick", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 422, f"缺 tenant 竟被接受（rc={r.status_code}）：{r.text[:200]}"


def test_tick_unknown_or_suspended_tenant_is_404(client, monkeypatch):
    """守什么：未知租户 / **停用**租户都不得跑定时刷新（用 `resolve_*` 只返 active）。"""
    monkeypatch.setenv("KNOT_SCHEDULER_TOKEN", "secret123")
    r = client.post("/api/bi/scheduler/tick?tenant=no-such-co",
                    headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 404, f"未知租户竟被接受（rc={r.status_code}）"

    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'susp','S','suspended','tenants/2')")
    conn.commit()
    conn.close()
    r2 = client.post("/api/bi/scheduler/tick?tenant=susp",
                     headers={"Authorization": "Bearer secret123"})
    assert r2.status_code == 404, f"停用租户竟跑了定时刷新（rc={r2.status_code}）"
