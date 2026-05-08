"""tests/integration/test_api_smoke.py — 端到端集成测试（v0.3.3 收官）

覆盖 4 层链路：api → services → repositories → models（不命中 LLM/Doris）。
跑前 init_db() 创建 tmp SQLite + seed admin；跑后清理。
"""


def test_healthz_returns_200(client):
    """v0.2.x 起的 health endpoint 仍工作。"""
    # /healthz 不一定挂载；用 /docs 替代证明 app 启动正常
    r = client.get("/docs")
    assert r.status_code == 200


def test_app_has_61_routes(client):
    """4-PATCH 重构未丢失任何端点 — 资深关心的回归项。
    v0.4.0 加 /api/messages/{id}/export.csv → 54 → 55。
    v0.4.1 加 saved_reports 6 路由（list/pin/run/update/delete + export.csv）→ 55 → 61。
    （手册原写 62 算错 1 路由，commit #8 docs sync 时一并修正。）"""
    from bi_agent.main import app
    assert len(app.routes) == 61


# ── 登录链路（api → services.auth_service → repositories.user_repo） ──

def test_login_seed_admin_succeeds(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"


def test_login_wrong_password_401(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_401(client):
    r = client.post("/api/auth/login", json={"username": "noexist", "password": "x"})
    assert r.status_code == 401


# ── /api/auth/me（JWT 解析 → user_repo.get_user_by_id） ──

def test_auth_me_with_valid_token(client, auth_headers):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_auth_me_without_token_403(client):
    """FastAPI HTTPBearer 默认无 token 返 403（不是 401）。"""
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)


def test_auth_me_invalid_token_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


# ── 会话 CRUD（api → services → repositories.conversation_repo） ──

def test_conversation_create_list_delete(client, auth_headers):
    create = client.post("/api/conversations", json={"title": "集成测试"}, headers=auth_headers)
    assert create.status_code == 200
    cid = create.json()["id"]

    listing = client.get("/api/conversations", headers=auth_headers)
    assert listing.status_code == 200
    titles = [c["title"] for c in listing.json()]
    assert "集成测试" in titles

    delete = client.delete(f"/api/conversations/{cid}", headers=auth_headers)
    assert delete.status_code == 200

    after = client.get("/api/conversations", headers=auth_headers)
    assert all(c["id"] != cid for c in after.json())


# ── Catalog admin 编辑（api.catalog → services.knot.catalog → repositories.settings_repo） ──

def test_catalog_get_returns_default(client, auth_headers):
    r = client.get("/api/admin/catalog", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "current" in body
    assert "defaults" in body
    assert body["source"] in ("example", "real", "empty")


def test_catalog_put_business_rules_then_reset(client, auth_headers):
    # PUT 注入 DB 覆盖
    r = client.put(
        "/api/admin/catalog",
        json={"business_rules": "## 集成测试规则\n- 测试用户排除"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "db"

    # GET 应返回 db 来源
    r2 = client.get("/api/admin/catalog", headers=auth_headers)
    assert "集成测试规则" in r2.json()["current"]["business_rules"]

    # POST reset 回到默认
    r3 = client.post("/api/admin/catalog/reset",
                     json={"fields": ["business_rules"]}, headers=auth_headers)
    assert r3.status_code == 200
    assert "business_rules" in r3.json()["cleared"]


# ── few-shots admin（api.few_shots → repositories.few_shot_repo） ──

def test_few_shot_crud(client, auth_headers):
    create = client.post(
        "/api/few-shots",
        json={"question": "测试问题", "sql": "SELECT 1", "type": "metric", "is_active": 1},
        headers=auth_headers,
    )
    assert create.status_code == 200
    fid = create.json()["id"]

    listing = client.get("/api/few-shots", headers=auth_headers)
    qs = [r["question"] for r in listing.json()]
    assert "测试问题" in qs

    update = client.put(
        f"/api/few-shots/{fid}",
        json={"sql": "SELECT 2"},
        headers=auth_headers,
    )
    assert update.status_code == 200

    delete = client.delete(f"/api/few-shots/{fid}", headers=auth_headers)
    assert delete.status_code == 200


# ── 权限检查（analyst 不能访问 admin 路由）──

# ── v0.4.0: intent 字段端到端流转（持久化 → 拉取 messages → JSON 含 intent） ──

def _seed_message_with_intent(client, headers, intent: str, question: str) -> int:
    create = client.post("/api/conversations", json={"title": "intent 测试"}, headers=headers)
    assert create.status_code == 200
    cid = create.json()["id"]
    from bi_agent.repositories.message_repo import save_message
    save_message(
        conv_id=cid, question=question,
        sql="SELECT 1", explanation="", confidence="high",
        rows=[{"x": 1}], db_error="",
        cost_usd=0.0, input_tokens=0, output_tokens=0, retry_count=0,
        intent=intent,
    )
    return cid


def test_get_messages_aliases_sql_text_to_sql(client, auth_headers):
    """v0.4.1.1 Bug 2 修复：GET /api/conversations/{id}/messages 必须把 SQLite 列名
    sql_text 同时暴露成 sql 键（与 SSE final 事件对齐），否则历史消息回放时
    前端 ResultBlock 解构 msg.sql 拿不到值，⭐ 收藏按钮 canPin 永远 false。"""
    create = client.post("/api/conversations", json={"title": "alias 测试"}, headers=auth_headers)
    cid = create.json()["id"]
    from bi_agent.repositories.message_repo import save_message
    save_message(
        conv_id=cid, question="昨天 GMV", sql="SELECT SUM(pay_amount) FROM orders",
        explanation="", confidence="high",
        rows=[{"gmv": 1}], db_error="",
        cost_usd=0.0, input_tokens=0, output_tokens=0, retry_count=0,
        intent="metric",
    )
    r = client.get(f"/api/conversations/{cid}/messages", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    m = body[0]
    assert m["sql"] == m["sql_text"]
    assert m["sql"] == "SELECT SUM(pay_amount) FROM orders"


def test_message_intent_metric_round_trips_in_json(client, auth_headers):
    """metric 类问题 → 消息 JSON 含 intent='metric'（手册 §7 用户补充 #1）。"""
    cid = _seed_message_with_intent(client, auth_headers, "metric", "昨天的 GMV")
    r = client.get(f"/api/conversations/{cid}/messages", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["intent"] == "metric"


def test_message_intent_detail_round_trips_in_json(client, auth_headers):
    """detail 类问题 → 消息 JSON 含 intent='detail'。"""
    cid = _seed_message_with_intent(client, auth_headers, "detail", "列出昨天注册用户")
    r = client.get(f"/api/conversations/{cid}/messages", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["intent"] == "detail"


# ── v0.4.1: saved_reports 端到端（pin → list → export → delete 不级联） ──

def _seed_msg_for_pin(client, headers, rows=None):
    create = client.post("/api/conversations", json={"title": "v0.4.1 smoke"}, headers=headers)
    cid = create.json()["id"]
    from bi_agent.repositories.message_repo import save_message
    mid = save_message(
        conv_id=cid, question="昨天 GMV", sql="SELECT SUM(pay_amount) FROM orders",
        explanation="", confidence="high",
        rows=rows or [{"gmv": 12345}], db_error="",
        cost_usd=0.0, input_tokens=0, output_tokens=0, retry_count=0,
        intent="metric",
    )
    return cid, mid


def test_saved_report_pin_then_list_includes_it(client, auth_headers):
    """端到端：pin → list 包含该 report，intent + display_hint 字段都在。"""
    _cid, mid = _seed_msg_for_pin(client, auth_headers)
    client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    r = client.get("/api/saved-reports", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(sr["source_message_id"] == mid for sr in body)
    sr = next(s for s in body if s["source_message_id"] == mid)
    assert sr["intent"] == "metric"
    assert sr["display_hint"] == "metric_card"


def test_saved_report_pin_export_lifecycle(client, auth_headers):
    """端到端：pin → export.csv → 验 BOM + 中文。"""
    rows = [{"用户": "张三", "金额": 100}]
    _cid, mid = _seed_msg_for_pin(client, auth_headers, rows=rows)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    r = client.get(f"/api/saved-reports/{sr_id}/export.csv", headers=auth_headers)
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "张三" in r.content.decode("utf-8-sig")


def test_delete_conversation_does_not_cascade_saved_reports(client, auth_headers):
    """R-S7 dangling 是预期：原 conversation 删 → message 没了 → saved_report 仍存活。"""
    cid, mid = _seed_msg_for_pin(client, auth_headers)
    pin = client.post(f"/api/messages/{mid}/pin", json={}, headers=auth_headers)
    sr_id = pin.json()["id"]
    # 删原 conversation（级联删 message）
    d = client.delete(f"/api/conversations/{cid}", headers=auth_headers)
    assert d.status_code == 200
    # saved_report 仍在列表
    r = client.get("/api/saved-reports", headers=auth_headers)
    assert any(sr["id"] == sr_id for sr in r.json())


def test_analyst_cannot_access_admin_routes(client, auth_headers):
    # 先创建 analyst 账号
    create = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "p", "role": "analyst"},
        headers=auth_headers,
    )
    assert create.status_code == 200

    # 用 analyst 登录
    login = client.post("/api/auth/login", json={"username": "alice", "password": "p"})
    assert login.status_code == 200
    analyst_token = login.json()["token"]

    # admin-only 路由应返回 403
    r = client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert r.status_code == 403
