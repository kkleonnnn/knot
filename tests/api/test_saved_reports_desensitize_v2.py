"""tests/api/test_saved_reports_desensitize_v2 — v0.6.3.0 段 5 B3 脱敏 V2 commit 1 守护测试。

缺口：saved_reports 对非 admin owner 0 strip/脱敏（conversations v0.6.0.17/19 已做，saved_reports 漏）
→ 非 admin 分析师查看/导出收藏报表泄漏原始 sql_text + 表名。

覆盖（与 conversations v0.6.0.17 平行）：
- 非 admin owner list/pin/update → report **0 sql_text**（R-PB-B3-1）
- admin → report **保留 sql_text**（R-PB-B3-3 admin 0 改动）
- run 结果 error desensitize 路径 fail-open 不崩（R-PB-B3-2；rows 不脱敏 R-PB-B3-4）
- return 前 assert sql_text not in（Stage 2 修订 1 — 测断言 list/pin/update 三端点）
"""
from __future__ import annotations


def _seed_message(client, headers, sql="SELECT amount FROM dwd_user_deal"):
    create = client.post("/api/conversations", json={"title": "B3 测试"}, headers=headers)
    cid = create.json()["id"]
    from knot.repositories.message_repo import save_message
    mid = save_message(
        conv_id=cid, question="昨天 GMV", sql=sql, explanation="", confidence="high",
        rows=[{"amount": 12345}], db_error="", cost_usd=0.0,
        input_tokens=0, output_tokens=0, retry_count=0, intent="metric",
    )
    return cid, mid


def _make_analyst(client, auth_headers, name="bob"):
    client.post("/api/admin/users",
                json={"username": name, "password": "p", "role": "analyst"}, headers=auth_headers)
    login = client.post("/api/auth/login", json={"username": name, "password": "p"})
    return {"Authorization": f"Bearer {login.json()['token']}"}


# ─── 非 admin owner：sql_text strip（list/pin/update 三端点）──────────

def test_non_admin_pin_strips_sql_text(client, auth_headers):
    analyst = _make_analyst(client, auth_headers)
    _cid, mid = _seed_message(client, analyst)
    r = client.post(f"/api/messages/{mid}/pin", json={}, headers=analyst)
    assert r.status_code == 200, r.text
    assert "sql_text" not in r.json(), "R-PB-B3-1：非 admin pin 返回必无 sql_text"
    assert "sql" not in r.json()


def test_non_admin_list_strips_sql_text(client, auth_headers):
    analyst = _make_analyst(client, auth_headers, "carol")
    _cid, mid = _seed_message(client, analyst)
    client.post(f"/api/messages/{mid}/pin", json={}, headers=analyst)
    r = client.get("/api/saved-reports", headers=analyst)
    assert r.status_code == 200
    reports = r.json()
    assert reports, "应有 1 收藏报表"
    for rep in reports:
        assert "sql_text" not in rep, "R-PB-B3-1：非 admin list 每项必无 sql_text"


def test_non_admin_update_strips_sql_text(client, auth_headers):
    analyst = _make_analyst(client, auth_headers, "dave")
    _cid, mid = _seed_message(client, analyst)
    rid = client.post(f"/api/messages/{mid}/pin", json={}, headers=analyst).json()["id"]
    r = client.put(f"/api/saved-reports/{rid}", json={"title": "改名"}, headers=analyst)
    assert r.status_code == 200
    assert "sql_text" not in r.json(), "R-PB-B3-1：非 admin update 返回必无 sql_text"


# ─── admin 0 改动（R-PB-B3-3）─────────────────────────────────────

def test_admin_keeps_sql_text(client, auth_headers):
    """admin 保留完整 sql_text（调试 + 业务目录维护 — 与 conversations 一致）。"""
    _cid, mid = _seed_message(client, auth_headers)
    r = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json().get("sql_text") == "SELECT amount FROM dwd_user_deal", "R-PB-B3-3：admin 保留 sql_text"


# ─── run 结果脱敏路径 fail-open + rows 不脱敏 ───────────────────────

def test_non_admin_run_result_fail_open_no_crash(client, auth_headers):
    """非 admin run → error desensitize 路径 fail-open 不崩（无 DB → error 非空但不崩）；rows 不脱敏。"""
    analyst = _make_analyst(client, auth_headers, "erin")
    _cid, mid = _seed_message(client, analyst)
    rid = client.post(f"/api/messages/{mid}/pin", json={}, headers=analyst).json()["id"]
    r = client.post(f"/api/saved-reports/{rid}/run", json={}, headers=analyst)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sql_text" not in body  # run 结果本就无 sql_text
    assert "error" in body  # error 字段存在（desensitize 路径走过 fail-open）
