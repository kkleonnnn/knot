"""tests/api/test_bi_reports.py — v0.8.5 (②a) BI 报表 API：CRUD + 权限门 + 脱敏。

R-BI-4 权限：admin 建/编/管/刷新；analyst 只读。R-BI-6：非 admin 读不含 sql_text。
R-BI-5/D7：写 SQL 存前校验 → 400。
"""


def _analyst_headers(client, auth_headers, uname="bi_analyst"):
    client.post("/api/admin/users", json={"username": uname, "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": uname, "password": "p"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_admin_folder_and_report_crud(client, auth_headers):
    fid = client.post("/api/bi/folders", json={"name": "平台经营"}, headers=auth_headers).json()["id"]
    r = client.post("/api/bi/reports", json={
        "title": "日汇总", "sql_text": "SELECT dt AS 日期 FROM t", "folder_id": fid,
    }, headers=auth_headers)
    assert r.status_code == 200
    rid = r.json()["id"]
    assert r.json()["folder_id"] == fid and r.json()["report_type"] == "wide_table"

    lst = client.get("/api/bi/reports", headers=auth_headers).json()
    assert any(x["id"] == rid for x in lst)

    got = client.get(f"/api/bi/reports/{rid}", headers=auth_headers).json()
    assert got["sql_text"] == "SELECT dt AS 日期 FROM t"  # admin 见 sql

    u = client.put(f"/api/bi/reports/{rid}", json={"title": "日汇总v2"}, headers=auth_headers)
    assert u.status_code == 200 and u.json()["title"] == "日汇总v2"

    assert client.delete(f"/api/bi/reports/{rid}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/bi/reports/{rid}", headers=auth_headers).status_code == 404


def test_create_rejects_write_sql_400(client, auth_headers):
    for bad in ("DELETE FROM users", "UPDATE t SET a=1", "DROP TABLE t"):
        r = client.post("/api/bi/reports", json={"title": "x", "sql_text": bad}, headers=auth_headers)
        assert r.status_code == 400, bad


def test_create_rejects_oversized_overlay_400(client, auth_headers):
    """R-BI-11 DoS 防：overlay 单元格上限（>500 → 400），防超大 overlay 客户端求值挂死。"""
    big = [{"row": i, "col": "A", "kind": "text", "value": "x"} for i in range(501)]
    r = client.post("/api/bi/reports",
                    json={"title": "t", "sql_text": "SELECT 1", "overlay_config": big},
                    headers=auth_headers)
    assert r.status_code == 400


def test_analyst_can_read_but_not_write(client, auth_headers):
    rid = client.post("/api/bi/reports", json={"title": "t", "sql_text": "SELECT secret FROM t"},
                      headers=auth_headers).json()["id"]
    ah = _analyst_headers(client, auth_headers)
    # 读允许，但 R-BI-6 脱 sql_text
    lst = client.get("/api/bi/reports", headers=ah)
    assert lst.status_code == 200
    row = next(x for x in lst.json() if x["id"] == rid)
    assert "sql_text" not in row
    assert "sql_text" not in client.get(f"/api/bi/reports/{rid}", headers=ah).json()
    # 写全 403（R-BI-4）
    assert client.post("/api/bi/reports", json={"title": "x", "sql_text": "SELECT 1"}, headers=ah).status_code == 403
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "y"}, headers=ah).status_code == 403
    assert client.delete(f"/api/bi/reports/{rid}", headers=ah).status_code == 403
    assert client.post(f"/api/bi/reports/{rid}/refresh", headers=ah).status_code == 403
    assert client.post("/api/bi/folders", json={"name": "x"}, headers=ah).status_code == 403


def test_refresh_no_datasource_returns_error(client, auth_headers):
    rid = client.post("/api/bi/reports", json={"title": "t", "sql_text": "SELECT 1"},
                      headers=auth_headers).json()["id"]
    out = client.post(f"/api/bi/reports/{rid}/refresh", headers=auth_headers)
    assert out.status_code == 200 and out.json()["error"]  # 无数据源 → error（不写快照）


def test_folder_delete_reparents_report_to_unfiled(client, auth_headers):
    fid = client.post("/api/bi/folders", json={"name": "p"}, headers=auth_headers).json()["id"]
    rid = client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                      headers=auth_headers).json()["id"]
    client.put(f"/api/bi/folders/{fid}", json={"name": "p2"}, headers=auth_headers)
    assert client.delete(f"/api/bi/folders/{fid}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/bi/reports/{rid}", headers=auth_headers).json()["folder_id"] is None
