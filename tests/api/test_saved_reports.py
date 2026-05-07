"""tests/api/test_saved_reports.py — v0.4.1 saved_reports 6 路由集成测试（8 条）。

覆盖：
- pin owner 成功 + already_pinned=False
- 同 message 二次 pin → 200 + already_pinned=True (R-12)
- 跨 user pin → 404 防 message_id 枚举
- list 仅返调用方自己的
- run owner 成功（数据源不可用时仍返 result，error 字段非空）
- run 跨 user → 404
- export.csv owner 成功 + utf-8-sig BOM
- delete owner → 404 on subsequent get
"""
from __future__ import annotations


def _seed_message(client, headers, intent="metric", rows=None, sql="SELECT 1") -> tuple[int, int]:
    """创建 conv，写一条带 intent 的 message，返回 (conv_id, message_id)。"""
    create = client.post("/api/conversations", json={"title": "saved_report 测试"}, headers=headers)
    assert create.status_code == 200, create.text
    cid = create.json()["id"]
    from bi_agent.repositories.message_repo import save_message
    mid = save_message(
        conv_id=cid, question="昨天的 GMV", sql=sql,
        explanation="", confidence="high",
        rows=rows or [{"gmv": 12345}], db_error="",
        cost_usd=0.0, input_tokens=0, output_tokens=0, retry_count=0,
        intent=intent,
    )
    return cid, mid


def test_pin_owner_success_returns_already_pinned_false(client, auth_headers):
    _cid, mid = _seed_message(client, auth_headers, intent="metric")
    r = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["already_pinned"] is False
    assert body["intent"] == "metric"
    assert body["display_hint"] == "metric_card"
    assert body["title"] == "昨天的 GMV"


def test_pin_same_message_twice_returns_already_pinned_true(client, auth_headers):
    """R-12 幂等端到端：第二次 pin → 200 + already_pinned=true。"""
    _cid, mid = _seed_message(client, auth_headers)
    first = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    second = client.post(f"/api/messages/{mid}/pin", json={"title": "覆盖标题"}, headers=auth_headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["already_pinned"] is False
    assert second.json()["already_pinned"] is True
    assert first.json()["id"] == second.json()["id"]
    # R-12 既存对象未被覆盖
    assert second.json()["title"] == first.json()["title"]


def test_pin_other_users_message_returns_404(client, auth_headers):
    """非所有者 analyst pin admin 的 message → 404 防 message_id 枚举。"""
    _cid, admin_mid = _seed_message(client, auth_headers)
    create = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "p", "role": "analyst"},
        headers=auth_headers,
    )
    assert create.status_code == 200
    login = client.post("/api/auth/login", json={"username": "alice", "password": "p"})
    analyst_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    r = client.post(f"/api/messages/{admin_mid}/pin", json={}, headers=analyst_headers)
    assert r.status_code == 404


def test_list_returns_only_caller_reports(client, auth_headers):
    """list 仅返自己 user_id 的 saved_reports。"""
    _cid, mid = _seed_message(client, auth_headers)
    client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    r = client.get("/api/saved-reports", headers=auth_headers)
    assert r.status_code == 200
    titles = [sr["title"] for sr in r.json()]
    assert "昨天的 GMV" in titles
    # analyst 看不到
    create = client.post(
        "/api/admin/users",
        json={"username": "bob", "password": "p", "role": "analyst"},
        headers=auth_headers,
    )
    assert create.status_code == 200
    login = client.post("/api/auth/login", json={"username": "bob", "password": "p"})
    analyst_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    r2 = client.get("/api/saved-reports", headers=analyst_headers)
    assert r2.status_code == 200 and r2.json() == []


def test_run_owner_returns_result_with_error_when_no_engine(client, auth_headers):
    """admin 在测试环境下没接 doris；run 应返 200 但 error 字段非空（不是 500）。"""
    _cid, mid = _seed_message(client, auth_headers)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    r = client.post(f"/api/saved-reports/{sr_id}/run", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # 测试环境无 doris 引擎；service 走 fallback 链最终返 error 字符串而非抛
    assert "error" in body
    assert "rows" in body  # 即使错误也返结构化 dict


def test_run_other_users_report_returns_404(client, auth_headers):
    _cid, mid = _seed_message(client, auth_headers)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    create = client.post(
        "/api/admin/users",
        json={"username": "carol", "password": "p", "role": "analyst"},
        headers=auth_headers,
    )
    assert create.status_code == 200
    login = client.post("/api/auth/login", json={"username": "carol", "password": "p"})
    analyst_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    r = client.post(f"/api/saved-reports/{sr_id}/run", headers=analyst_headers)
    assert r.status_code == 404


def test_export_csv_owner_success_with_bom(client, auth_headers):
    """复用 v0.4.0 export_service：导出带 utf-8-sig BOM。"""
    rows = [{"用户": "张三", "金额": 100}, {"用户": "李四", "金额": 200}]
    _cid, mid = _seed_message(client, auth_headers, rows=rows)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    r = client.get(f"/api/saved-reports/{sr_id}/export.csv", headers=auth_headers)
    assert r.status_code == 200
    body = r.content
    assert body.startswith(b"\xef\xbb\xbf")
    text = body.decode("utf-8-sig")
    assert "张三" in text and "李四" in text and "用户,金额" in text
    cd = r.headers.get("content-disposition", "")
    assert f"saved_report_{sr_id}.csv" in cd


def test_delete_owner_then_404_on_run(client, auth_headers):
    _cid, mid = _seed_message(client, auth_headers)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    d = client.delete(f"/api/saved-reports/{sr_id}", headers=auth_headers)
    assert d.status_code == 200
    after = client.post(f"/api/saved-reports/{sr_id}/run", headers=auth_headers)
    assert after.status_code == 404
