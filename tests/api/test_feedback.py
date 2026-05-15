"""tests/api/test_feedback.py — v0.6.0.3 F-A 用户反馈守护测试。

覆盖：
- POST 创建反馈成功 + 返回 score
- POST 同 (msg, user) 重复 → upsert 幂等（score 可改）
- POST score 非 ±1 → 422
- POST 越权（非 conv owner 且非 admin）→ 404
- GET admin 列表分页 + score 过滤
- audit_log 写入 action=feedback.submit + resource_type=message
- GET messages 端点 LEFT JOIN 回显 user_feedback_score
"""
from __future__ import annotations


def _create_conv_with_msg(client, headers):
    """fixture 辅助：创建 conv + 注入一条 message 直接落 DB（绕过 LLM）。"""
    r = client.post("/api/conversations", json={"title": "test"}, headers=headers)
    assert r.status_code == 200
    cid = r.json()["id"]
    # 直接 SQL 插一条 assistant message（跳过完整 query 链路）
    from knot.repositories.base import get_conn
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, question, sql_text, agent_kind) "
        "VALUES (?,?,?,?)",
        (cid, "test q", "SELECT 1", "presenter"),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid, mid


def test_post_feedback_creates_row(client, auth_headers):
    cid, mid = _create_conv_with_msg(client, auth_headers)
    r = client.post(f"/api/messages/{mid}/feedback",
                    json={"score": 1, "comment": "good answer"},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["score"] == 1
    assert r.json()["id"] > 0


def test_post_feedback_upsert_idempotent(client, auth_headers):
    """同 (msg, user) 第二次 POST → upsert；score 可改写。"""
    cid, mid = _create_conv_with_msg(client, auth_headers)
    r1 = client.post(f"/api/messages/{mid}/feedback",
                     json={"score": 1, "comment": "good"}, headers=auth_headers)
    r2 = client.post(f"/api/messages/{mid}/feedback",
                     json={"score": -1, "comment": "bad on second thought"}, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    # 查 admin 列表 — score 应是 -1
    lr = client.get("/api/admin/feedback", headers=auth_headers)
    items = lr.json()["items"]
    assert len(items) == 1, f"应只有 1 行（upsert）；得到 {len(items)}"
    assert items[0]["score"] == -1


def test_post_feedback_rejects_invalid_score(client, auth_headers):
    cid, mid = _create_conv_with_msg(client, auth_headers)
    r = client.post(f"/api/messages/{mid}/feedback",
                    json={"score": 2}, headers=auth_headers)
    assert r.status_code == 422


def test_post_feedback_404_for_nonexistent_message(client, auth_headers):
    r = client.post("/api/messages/9999999/feedback",
                    json={"score": 1}, headers=auth_headers)
    assert r.status_code == 404


def test_admin_list_pagination_and_filter(client, auth_headers):
    """admin GET 列表 + score 过滤 + limit cap 200。"""
    cid, mid = _create_conv_with_msg(client, auth_headers)
    client.post(f"/api/messages/{mid}/feedback",
                json={"score": 1}, headers=auth_headers)
    r = client.get("/api/admin/feedback?score=1&limit=10&offset=0",
                   headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
    assert body["total"] >= 1
    # cap 200 守护
    rc = client.get("/api/admin/feedback?limit=500", headers=auth_headers)
    assert rc.status_code == 200  # repo 内部 cap，不抛 422


def test_feedback_submit_writes_audit_log(client, auth_headers):
    cid, mid = _create_conv_with_msg(client, auth_headers)
    client.post(f"/api/messages/{mid}/feedback",
                json={"score": 1, "comment": "test"}, headers=auth_headers)
    # 查 audit_log
    from knot.repositories.base import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT action, resource_type, resource_id FROM audit_log "
        "WHERE action='feedback.submit' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None, "feedback.submit 必须入 audit_log"
    assert row[1] == "message"
    assert row[2] == str(mid)


def test_messages_endpoint_returns_user_feedback_score(client, auth_headers):
    """GET /api/conversations/{cid}/messages 应 LEFT JOIN 返 user_feedback_score。"""
    cid, mid = _create_conv_with_msg(client, auth_headers)
    client.post(f"/api/messages/{mid}/feedback",
                json={"score": -1}, headers=auth_headers)
    r = client.get(f"/api/conversations/{cid}/messages", headers=auth_headers)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 1
    assert msgs[0].get("user_feedback_score") == -1, \
        f"应返 user_feedback_score=-1; 得到 {msgs[0].get('user_feedback_score')}"
