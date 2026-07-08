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


def test_export_csv_400_when_no_rows(client, auth_headers):
    rid = client.post("/api/bi/reports", json={"title": "t", "sql_text": "SELECT 1"},
                      headers=auth_headers).json()["id"]
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers).status_code == 400


def test_export_csv_neutralizes_injection_r_bi_12(client, auth_headers):
    """R-BI-12：BI 导出复用 export_service（v0.8.4 中性化）→ 文本 =SUMIF 前缀 '。"""
    from knot.repositories import bi_report_repo as repo
    rid = client.post("/api/bi/reports", json={"title": "t", "sql_text": "SELECT 1"},
                      headers=auth_headers).json()["id"]
    repo.update_last_run(rid, rows_json='[{"a": 1, "b": "=SUMIF(x)"}]', truncated=0,
                         elapsed_ms=1, run_at="2026-07-07 09:00:00", last_run_by=1)
    r = client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers)
    assert r.status_code == 200
    body = r.content.decode("utf-8-sig")
    assert "'=SUMIF(x)" in body   # 注入中性化（首字符 = → 前缀 '）


def test_folder_delete_reparents_report_to_unfiled(client, auth_headers):
    fid = client.post("/api/bi/folders", json={"name": "p"}, headers=auth_headers).json()["id"]
    rid = client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                      headers=auth_headers).json()["id"]
    client.put(f"/api/bi/folders/{fid}", json={"name": "p2"}, headers=auth_headers)
    assert client.delete(f"/api/bi/folders/{fid}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/bi/reports/{rid}", headers=auth_headers).json()["folder_id"] is None


# ── ②b 仪表盘 tile API（tiles payload / 脱敏 / DoS / refresh / 导出闸）────────────

def _dash(client, auth_headers, tiles, data_source_id=None):
    body = {"title": "仪表盘", "sql_text": "SELECT 1", "report_type": "dashboard", "tiles": tiles}
    if data_source_id is not None:
        body["data_source_id"] = data_source_id
    return client.post("/api/bi/reports", json=body, headers=auth_headers)


def test_create_dashboard_with_tiles_and_per_tile_desensitize(client, auth_headers):
    r = _dash(client, auth_headers, [
        {"tile_type": "kpi", "title": "量", "sql_text": "SELECT secret FROM t"},
        {"tile_type": "line", "title": "趋势", "sql_text": "SELECT d,v FROM t", "sort_order": 1},
    ])
    assert r.status_code == 200
    rid = r.json()["id"]
    assert [t["title"] for t in r.json()["tiles"]] == ["量", "趋势"]
    # admin GET 见 tile sql
    admin_tiles = client.get(f"/api/bi/reports/{rid}", headers=auth_headers).json()["tiles"]
    assert admin_tiles[0]["sql_text"] == "SELECT secret FROM t"
    # analyst GET 每 tile 无 sql_text（R-BI-6 per-tile）
    ah = _analyst_headers(client, auth_headers)
    an_tiles = client.get(f"/api/bi/reports/{rid}", headers=ah).json()["tiles"]
    assert an_tiles and all("sql_text" not in t for t in an_tiles)


def test_tile_write_sql_rejected_400(client, auth_headers):
    r = _dash(client, auth_headers, [{"tile_type": "kpi", "sql_text": "DROP TABLE t"}])
    assert r.status_code == 400


def test_oversized_tiles_400(client, auth_headers):
    big = [{"tile_type": "kpi", "sql_text": "SELECT 1"} for _ in range(31)]
    assert _dash(client, auth_headers, big).status_code == 400


def test_refresh_dashboard_per_tile_and_export_gated(client, auth_headers, monkeypatch):
    from knot.services import bi_report_service as svc
    rid = _dash(client, auth_headers, [
        {"tile_type": "kpi", "sql_text": "SELECT 1"},
        {"tile_type": "table", "sql_text": "SELECT 2"},
    ], data_source_id=7).json()["id"]
    # mock 引擎/执行（一个 tile 成功、一个报错 → per-tile 隔离）
    monkeypatch.setattr(svc.engine_cache, "get_engine_for_source", lambda sid: object())
    calls = {"n": 0}
    def _exec(eng, sql):
        calls["n"] += 1
        return ([{"v": 1}], None) if calls["n"] == 1 else ([], "表不存在")
    monkeypatch.setattr(svc.db_connector, "execute_query", _exec)
    out = client.post(f"/api/bi/reports/{rid}/refresh", headers=auth_headers).json()
    assert out["report_type"] == "dashboard" and out["tile_count"] == 2 and out["error_count"] == 1
    # B-7：dashboard 导出闸 → 400（不导报表级空/旧数据）
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers).status_code == 400
