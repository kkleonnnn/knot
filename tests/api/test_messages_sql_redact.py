"""v0.6.0.17 — GET /api/conversations/{id}/messages sql_text 脱敏守护。

非 admin 用户：返回中 sql_text + sql 字段必须不存在
admin 用户：返回中 sql_text + sql 字段必须保留（调试 + 业务目录维护需要）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from knot.main import app
    return TestClient(app)


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _create_conv_with_message(client, token):
    """Create a conv + insert a message via repo (bypassing query to avoid LLM)."""
    r = client.post("/api/conversations", json={"title": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]
    from knot.repositories import message_repo
    message_repo.save_message(
        conv_id=conv_id, question="test q", sql="SELECT * FROM dwd_user_deal",
        explanation="洞察", confidence="high", rows=[{"x": 1}],
        db_error="", cost_usd=0.001, input_tokens=10, output_tokens=20,
        retry_count=0, agent_kind="sql_planner",
    )
    return conv_id


def test_admin_sees_sql_text(client):
    """admin 用户：sql_text + sql 字段保留。"""
    token, _ = _login(client, "admin", "admin123")
    conv_id = _create_conv_with_message(client, token)
    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 1
    msg = msgs[-1]
    # admin 角色保留 sql_text + sql
    assert "sql_text" in msg, f"admin 应保留 sql_text；keys={list(msg.keys())}"
    assert "sql" in msg, f"admin 应保留 sql；keys={list(msg.keys())}"
    assert msg["sql_text"] == "SELECT * FROM dwd_user_deal"


def test_non_admin_sql_text_stripped(client):
    """非 admin 用户：sql_text + sql 字段移除（v0.6.0.17 脱敏）。"""
    # 先用 admin 创建一个 user
    admin_token, _ = _login(client, "admin", "admin123")
    import time
    uname = f"biztester_{int(time.time() * 1000)}"
    r = client.post("/api/admin/users",
                    json={"username": uname, "password": "test12345", "display_name": "Biz Tester", "role": "analyst"},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code in (200, 201), r.text

    # 用户登录
    user_token, user = _login(client, uname, "test12345")
    assert user["role"] == "analyst"

    # 让用户创建一个对话 + 插一条消息
    conv_id = _create_conv_with_message(client, user_token)

    # 用户取自己的消息 → sql_text / sql 应被移除
    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 1
    msg = msgs[-1]
    assert "sql_text" not in msg, f"非 admin 不应回 sql_text；keys={list(msg.keys())}"
    assert "sql" not in msg, f"非 admin 不应回 sql；keys={list(msg.keys())}"
    # 其他字段保留
    assert "question" in msg
    assert "explanation" in msg
    assert "rows_json" in msg or "rows" in msg
