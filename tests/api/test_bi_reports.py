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
    def _exec(eng, sql, **kw):
        calls["n"] += 1
        return ([{"v": 1}], None) if calls["n"] == 1 else ([], "表不存在")
    monkeypatch.setattr(svc.db_connector, "execute_query", _exec)
    out = client.post(f"/api/bi/reports/{rid}/refresh", headers=auth_headers).json()
    assert out["report_type"] == "dashboard" and out["tile_count"] == 2 and out["error_count"] == 1
    # B-7：dashboard 导出闸 → 400（不导报表级空/旧数据）
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers).status_code == 400


# ── v0.8.8 ③ 目录拖拽排序 ────────────────────────────────────────────────────────

def _mk_report(client, auth_headers, title):
    return client.post("/api/bi/reports", json={"title": title, "sql_text": "SELECT 1"},
                       headers=auth_headers).json()["id"]


def test_reorder_reports_admin_persists_order(client, auth_headers):
    a = _mk_report(client, auth_headers, "A")
    b = _mk_report(client, auth_headers, "B")
    c = _mk_report(client, auth_headers, "C")
    r = client.put("/api/bi/reorder/reports", json={"ordered_ids": [c, a, b]}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    ids = [x["id"] for x in client.get("/api/bi/reports", headers=auth_headers).json()]
    assert ids == [c, a, b]                                      # list 按 sort_order


def test_reorder_folders_admin_persists_order(client, auth_headers):
    f1 = client.post("/api/bi/folders", json={"name": "F1"}, headers=auth_headers).json()["id"]
    f2 = client.post("/api/bi/folders", json={"name": "F2"}, headers=auth_headers).json()["id"]
    client.put("/api/bi/reorder/folders", json={"ordered_ids": [f2, f1]}, headers=auth_headers)
    ids = [x["id"] for x in client.get("/api/bi/folders", headers=auth_headers).json()]
    assert ids == [f2, f1]


def test_reorder_analyst_403(client, auth_headers):
    a = _mk_report(client, auth_headers, "A")
    ah = _analyst_headers(client, auth_headers)
    assert client.put("/api/bi/reorder/reports", json={"ordered_ids": [a]}, headers=ah).status_code == 403
    assert client.put("/api/bi/reorder/folders", json={"ordered_ids": []}, headers=ah).status_code == 403


def test_reorder_oversized_400(client, auth_headers):
    r = client.put("/api/bi/reorder/reports", json={"ordered_ids": list(range(1001))}, headers=auth_headers)
    assert r.status_code == 400


def test_create_tile_overlay_oversized_400(client, auth_headers):
    # v0.8.9：per-tile 公式行单元格上限（≤500）—— 防 viz_config 塞超大 overlay → 客户端求值 DoS
    big = [{"col": "A", "row": 1, "kind": "text", "value": "x"}] * 501
    r = client.post("/api/bi/reports", json={
        "title": "d", "sql_text": "SELECT 1", "report_type": "tabbed",
        "tiles": [{"tile_type": "table", "title": "p", "sql_text": "SELECT 1", "viz_config": {"overlay": big}}],
    }, headers=auth_headers)
    assert r.status_code == 400


def test_create_tile_nondict_viz_config_no_500(client, auth_headers):
    # 对抗复核 #4：viz_config 为非 dict（串）→ _check_tiles_size 须跳过不崩（原 .get 抛 AttributeError → 500）
    r = client.post("/api/bi/reports", json={
        "title": "d", "sql_text": "SELECT 1", "report_type": "tabbed",
        "tiles": [{"tile_type": "table", "title": "p", "sql_text": "SELECT 1", "viz_config": "notadict"}],
    }, headers=auth_headers)
    assert r.status_code != 500


def test_tabbed_export_csv_current_page_and_xlsx_multisheet(client, auth_headers, monkeypatch):
    # v0.8.9 #3：多页表 CSV=当前页（中文 label 表头）+ Excel=多 sheet 全页
    from knot.services import bi_report_service as svc
    rid = client.post("/api/bi/reports", json={
        "title": "运营", "sql_text": "SELECT 1", "report_type": "tabbed", "data_source_id": 1,
        "tiles": [
            {"tile_type": "table", "title": "日汇总", "sql_text": "SELECT 1", "viz_config": {"columns": {"a": {"label": "甲列"}}}},
            {"tile_type": "table", "title": "周汇总", "sql_text": "SELECT 1", "viz_config": {}},
        ],
    }, headers=auth_headers).json()["id"]
    monkeypatch.setattr(svc.engine_cache, "get_engine_for_source", lambda sid: object())
    monkeypatch.setattr(svc.db_connector, "execute_query", lambda eng, sql, **kw: ([{"a": 1}, {"a": 2}], None))
    client.post(f"/api/bi/reports/{rid}/refresh", headers=auth_headers)
    tid = client.get(f"/api/bi/reports/{rid}", headers=auth_headers).json()["tiles"][0]["id"]
    csv = client.get(f"/api/bi/reports/{rid}/export.csv?tile_id={tid}", headers=auth_headers)
    assert csv.status_code == 200 and "甲列" in csv.content.decode("utf-8-sig")   # 中文 label 表头
    xl = client.get(f"/api/bi/reports/{rid}/export.xlsx", headers=auth_headers)
    assert xl.status_code == 200 and len(xl.content) > 100                        # 多 sheet xlsx 非空


def test_dashboard_export_still_gated_400(client, auth_headers):
    # 仪表盘（图表板块）不支持表格导出 → 400（不因 v0.8.9 tabbed 放开而误开）
    rid = client.post("/api/bi/reports", json={
        "title": "dash", "sql_text": "SELECT 1", "report_type": "dashboard",
        "tiles": [{"tile_type": "kpi", "title": "k", "sql_text": "SELECT 1", "viz_config": {"valueCol": "a"}}],
    }, headers=auth_headers).json()["id"]
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers).status_code == 400
    assert client.get(f"/api/bi/reports/{rid}/export.xlsx", headers=auth_headers).status_code == 400


# ── da-asst 只读报表解读（v0.8.10 §5 ③ 提前）────────────────────────────────────────

def test_analyze_report_da_asst(client, auth_headers, monkeypatch):
    import knot.services.agents.da_asst as da
    rid = client.post("/api/bi/reports", json={
        "title": "解读测试", "sql_text": "SELECT dt AS 日期 FROM t"}, headers=auth_headers).json()["id"]

    async def fake(report, question, history=None, model_key=""):
        assert report["title"] == "解读测试"                       # 上下文确实带了本报表
        return {"answer": f"已解读：{question}", "input_tokens": 1, "output_tokens": 2, "cost_usd": 0.0}
    monkeypatch.setattr(da, "arun_da_asst", fake)

    r = client.post(f"/api/bi/reports/{rid}/analyze",
                    json={"question": "趋势如何？", "history": []}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["answer"] == "已解读：趋势如何？"
    # 空问题 → 400；报表不存在 → 404
    assert client.post(f"/api/bi/reports/{rid}/analyze",
                       json={"question": "   "}, headers=auth_headers).status_code == 400
    assert client.post("/api/bi/reports/999999/analyze",
                       json={"question": "x"}, headers=auth_headers).status_code == 404


def test_analyze_read_only_desensitized_for_analyst(client, auth_headers, monkeypatch):
    """R-BI-4/6：analyst（非 admin）可只读解读；da-asst 拿到的是脱敏 DTO（无 sql_text）。"""
    import knot.services.agents.da_asst as da
    rid = client.post("/api/bi/reports", json={
        "title": "脱敏解读", "sql_text": "SELECT secret FROM t"}, headers=auth_headers).json()["id"]
    seen = {}

    async def fake(report, question, history=None, model_key=""):
        seen["has_sql"] = "sql_text" in report
        return {"answer": "ok", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    monkeypatch.setattr(da, "arun_da_asst", fake)

    ah = _analyst_headers(client, auth_headers)
    r = client.post(f"/api/bi/reports/{rid}/analyze", json={"question": "x"}, headers=ah)
    assert r.status_code == 200
    assert seen["has_sql"] is False                                # analyst 路径脱敏 → 不下发 sql_text


def test_analyze_history_too_long_400(client, auth_headers):
    rid = client.post("/api/bi/reports", json={
        "title": "h", "sql_text": "SELECT 1"}, headers=auth_headers).json()["id"]
    big = [{"role": "user", "content": "x"} for _ in range(25)]     # > _MAX_ANALYZE_HISTORY(24)
    assert client.post(f"/api/bi/reports/{rid}/analyze",
                       json={"question": "x", "history": big}, headers=auth_headers).status_code == 400


def test_analyze_blocked_when_over_monthly_budget(client, auth_headers, monkeypatch):
    """成本控制：月预算 status=='block' → 402 pre-block，绝不触发 LLM 花费（脚本 loop 财务 DoS 护栏）。"""
    import knot.services.agents.da_asst as da
    import knot.services.budget_service as budget_service
    rid = client.post("/api/bi/reports", json={
        "title": "预算门", "sql_text": "SELECT 1"}, headers=auth_headers).json()["id"]
    called = {"llm": False}

    async def fake(*a, **k):
        called["llm"] = True
        return {"answer": "x", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    monkeypatch.setattr(da, "arun_da_asst", fake)
    monkeypatch.setattr(budget_service, "check_user_monthly_budget", lambda uid: ("block", {"threshold": 1.0}))

    r = client.post(f"/api/bi/reports/{rid}/analyze", json={"question": "x"}, headers=auth_headers)
    assert r.status_code == 402
    assert called["llm"] is False                                  # over-budget → LLM 未被调用


# ── v0.8.12 RBAC 端点强制 + 权限管理（**用户**×目录 + 未分组逐报表）───────────────────

def _analyst(client, auth_headers, uname="bi_analyst"):
    """建 analyst → 返 (headers, uid)。"""
    client.post("/api/admin/users", json={"username": uname, "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": uname, "password": "p"}).json()["token"]
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=auth_headers).json()
               if u["username"] == uname)
    return {"Authorization": f"Bearer {tok}"}, uid


def _grant(client, auth_headers, user_id, *, folder_id=None, report_id=None, **perms):
    body = {"user_id": user_id, "folder_id": folder_id, "report_id": report_id,
            "can_schedule": False, "can_edit": False, "can_export": False, "can_share": False, **perms}
    return client.put("/api/bi/permissions", json=body, headers=auth_headers)


def test_rbac_edit_denied_then_folder_granted(client, auth_headers):
    fid = client.post("/api/bi/folders", json={"name": "运营"}, headers=auth_headers).json()["id"]
    rid = client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                      headers=auth_headers).json()["id"]
    ah, uid = _analyst(client, auth_headers)
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "r2"}, headers=ah).status_code == 403   # 无 grant
    assert _grant(client, auth_headers, uid, folder_id=fid, can_edit=True).status_code == 200
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "r2"}, headers=ah).status_code == 200    # 授权后可
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "r3"}, headers=auth_headers).status_code == 200  # admin 恒可


def test_rbac_user_scoped(client, auth_headers):
    """按用户：授 A 不影响 B（同角色不同权限）。"""
    fid = client.post("/api/bi/folders", json={"name": "运营"}, headers=auth_headers).json()["id"]
    rid = client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                      headers=auth_headers).json()["id"]
    ah_a, uid_a = _analyst(client, auth_headers, "user_a")
    ah_b, _uid_b = _analyst(client, auth_headers, "user_b")
    _grant(client, auth_headers, uid_a, folder_id=fid, can_edit=True)   # 只授 A
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "x"}, headers=ah_a).status_code == 200   # A 可
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "y"}, headers=ah_b).status_code == 403   # B 不可


def test_rbac_export_tightened(client, auth_headers, monkeypatch):
    from knot.services import bi_report_service as bsvc
    fid = client.post("/api/bi/folders", json={"name": "F"}, headers=auth_headers).json()["id"]
    rid = client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid,
                      "data_source_id": 1}, headers=auth_headers).json()["id"]   # 有 sid → refresh 走 mock engine 写快照
    monkeypatch.setattr(bsvc.engine_cache, "get_engine_for_source", lambda sid: object())
    monkeypatch.setattr(bsvc.db_connector, "execute_query", lambda e, s, **k: ([{"a": 1}], None))
    client.post(f"/api/bi/reports/{rid}/refresh", headers=auth_headers)
    ah, uid = _analyst(client, auth_headers)
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=ah).status_code == 403   # 收紧：无 grant 拒
    _grant(client, auth_headers, uid, folder_id=fid, can_export=True)
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=ah).status_code == 200
    assert client.get(f"/api/bi/reports/{rid}/export.csv", headers=auth_headers).status_code == 200  # admin 恒可


def test_rbac_ungrouped_per_report(client, auth_headers):
    rid = client.post("/api/bi/reports", json={"title": "u", "sql_text": "SELECT 1"},
                      headers=auth_headers).json()["id"]                       # 未分组
    ah, uid = _analyst(client, auth_headers)
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "x"}, headers=ah).status_code == 403
    _grant(client, auth_headers, uid, report_id=rid, can_edit=True)
    assert client.put(f"/api/bi/reports/{rid}", json={"title": "x"}, headers=ah).status_code == 200


def test_rbac_create_gate(client, auth_headers):
    fid = client.post("/api/bi/folders", json={"name": "F"}, headers=auth_headers).json()["id"]
    ah, uid = _analyst(client, auth_headers)
    assert client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                       headers=ah).status_code == 403                          # 无目录 edit
    assert client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1"},
                       headers=ah).status_code == 403                          # 未分组建报表仅 admin
    _grant(client, auth_headers, uid, folder_id=fid, can_edit=True)
    assert client.post("/api/bi/reports", json={"title": "r", "sql_text": "SELECT 1", "folder_id": fid},
                       headers=ah).status_code == 200


def test_permissions_api_admin_only_and_validation(client, auth_headers):
    ah, uid = _analyst(client, auth_headers)
    assert client.get("/api/bi/permissions", headers=ah).status_code == 403    # analyst 不能读权限表
    assert client.put("/api/bi/permissions", json={"user_id": uid, "can_edit": True},
                      headers=auth_headers).status_code == 400                 # 无 folder/report
    assert client.put("/api/bi/permissions", json={"user_id": uid, "folder_id": 1, "report_id": 2,
                      "can_edit": True}, headers=auth_headers).status_code == 400   # 两个都给
    _grant(client, auth_headers, uid, folder_id=1, can_edit=True)
    lst = client.get("/api/bi/permissions", headers=auth_headers).json()
    assert any(g["folder_id"] == 1 and g["user_id"] == uid and g["can_edit"] == 1 for g in lst)


def test_rbac_grant_cascade_on_report_delete(client, auth_headers):
    rid = client.post("/api/bi/reports", json={"title": "u", "sql_text": "SELECT 1"},
                      headers=auth_headers).json()["id"]
    _ah, uid = _analyst(client, auth_headers)
    _grant(client, auth_headers, uid, report_id=rid, can_edit=True)
    assert any(g["report_id"] == rid for g in client.get("/api/bi/permissions", headers=auth_headers).json())
    client.delete(f"/api/bi/reports/{rid}", headers=auth_headers)
    assert not any(g["report_id"] == rid for g in client.get("/api/bi/permissions", headers=auth_headers).json())

