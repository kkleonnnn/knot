"""v0.8.21 体验 — 数据源列表探测解耦：列表端点不内联探测（不可达源不再卡分钟级），/status 才探测。"""
from __future__ import annotations


def _mk_source(client, auth_headers, host="10.255.255.1"):
    r = client.post("/api/admin/datasources", json={
        "name": "d1", "description": "", "db_host": host, "db_port": 9030,
        "db_user": "u", "db_password": "p", "db_database": "x", "db_type": "doris", "http_config": "",
    }, headers=auth_headers)
    assert r.status_code == 200, r.text


def test_list_datasources_no_inline_probe(client, auth_headers, monkeypatch):
    """列表端点**不调 _test_source**（解耦）→ status='checking'；/status 端点才探测。"""
    from knot.api.admin import datasources as ds
    _mk_source(client, auth_headers)
    called = {"n": 0}

    def _tracking(s):
        called["n"] += 1
        return "online"
    monkeypatch.setattr(ds, "_test_source", _tracking)

    r = client.get("/api/admin/datasources", headers=auth_headers)
    assert r.status_code == 200 and len(r.json()) >= 1
    assert called["n"] == 0, "列表端点不应内联探测（v0.8.21 解耦 —— 不可达源不再卡列表）"
    assert all(x["status"] == "checking" for x in r.json()), "未探测的源 status 应为 checking"

    r2 = client.get("/api/admin/datasources/status", headers=auth_headers)
    assert r2.status_code == 200
    assert called["n"] >= 1, "/status 端点才实际探测"
    assert isinstance(r2.json(), dict), "/status 返 {id: status}"


def test_status_endpoint_caches_result(client, auth_headers, monkeypatch):
    """/status 探测结果写缓存 → 之后列表端点 status 反映缓存（非恒 checking）。"""
    from knot.api.admin import datasources as ds
    _mk_source(client, auth_headers)
    monkeypatch.setattr(ds, "_test_source", lambda s: "online")
    client.get("/api/admin/datasources/status", headers=auth_headers)  # 写缓存
    r = client.get("/api/admin/datasources", headers=auth_headers)
    assert all(x["status"] == "online" for x in r.json()), "列表应取 /status 写入的缓存状态"


def test_list_requires_admin(client, auth_headers):
    """列表 + status 端点仍 admin-only（未松动鉴权）。"""
    login = client.post("/api/admin/users",
                        json={"username": "an2", "password": "pw12345", "role": "analyst"},
                        headers=auth_headers)
    assert login.status_code == 200
    tok = client.post("/api/auth/login", json={"username": "an2", "password": "pw12345"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/admin/datasources", headers=h).status_code == 403
    assert client.get("/api/admin/datasources/status", headers=h).status_code == 403
