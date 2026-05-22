"""v0.6.0.17 — GET /api/conversations/{id}/messages sql_text 脱敏守护。

非 admin 用户：返回中 sql_text + sql 字段必须不存在
admin 用户：返回中 sql_text + sql 字段必须保留（调试 + 业务目录维护需要）
"""
from __future__ import annotations

# v0.6.0.20: client fixture 从 tests/api/conftest.py 注入（含 must_change_password=0 reset）；
# 本文件不再定义局部 client fixture。


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _create_conv_with_message(client, token, explanation="洞察", db_error=""):
    """Create a conv + insert a message via repo (bypassing query to avoid LLM)."""
    r = client.post("/api/conversations", json={"title": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]
    from knot.repositories import message_repo
    message_repo.save_message(
        conv_id=conv_id, question="test q", sql="SELECT * FROM dwd_user_deal",
        explanation=explanation, confidence="high", rows=[{"x": 1}],
        db_error=db_error, cost_usd=0.001, input_tokens=10, output_tokens=20,
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


# ─── v0.6.0.19 脱敏链 3/3：explanation + db_error 文本表名脱敏 ──────────────


def _set_lexicon(token, lexicon: dict):
    """admin 通过 PUT /api/admin/catalog 配置 lexicon（reverse-lookup 别名源）。"""
    import requests  # noqa: F401 (TestClient 内部用)


def test_v060019_non_admin_explanation_desensitized(client):
    """v0.6.0.19 — analyst 看到的 explanation 中表名已替换为业务别名。"""
    admin_token, _ = _login(client, "admin", "admin123")

    # 1) admin 配置 catalog.lexicon （app.users → '用户'）
    r = client.put(
        "/api/admin/catalog",
        json={"lexicon": {"用户": ["app.users"]}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # 2) admin 创建一个 analyst
    import time
    uname = f"biz_v19_a_{int(time.time() * 1000)}"
    r = client.post(
        "/api/admin/users",
        json={"username": uname, "password": "test12345", "display_name": "Biz V19 A", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), r.text

    # 3) analyst 登录 + 创建 conv + 插 message（explanation 含 app.users）
    user_token, user = _login(client, uname, "test12345")
    assert user["role"] == "analyst"
    conv_id = _create_conv_with_message(
        client, user_token,
        explanation="基于 app.users 查询了用户行为；附加 app.users JOIN 关联",
    )

    # 4) analyst 取消息 → explanation 不含 app.users 字面，应被替换为 '用户'
    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    msgs = r.json()
    msg = msgs[-1]
    assert "app.users" not in msg["explanation"], f"未脱敏：{msg['explanation']}"
    assert "用户" in msg["explanation"]


def test_v060019_non_admin_db_error_desensitized(client):
    """v0.6.0.19 — analyst 看到的 db_error 中表名也被替换。"""
    admin_token, _ = _login(client, "admin", "admin123")
    r = client.put(
        "/api/admin/catalog",
        json={"lexicon": {"订单": ["app.orders"]}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    import time
    uname = f"biz_v19_b_{int(time.time() * 1000)}"
    r = client.post(
        "/api/admin/users",
        json={"username": uname, "password": "test12345", "display_name": "Biz V19 B", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), r.text

    user_token, _ = _login(client, uname, "test12345")
    conv_id = _create_conv_with_message(
        client, user_token,
        explanation="",
        db_error="Table app.orders not found in schema app",
    )

    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    msg = r.json()[-1]
    assert "app.orders" not in msg["db_error"], f"未脱敏 db_error：{msg['db_error']}"
    assert "订单" in msg["db_error"]


def test_v060019_admin_sees_raw_explanation_and_db_error(client):
    """v0.6.0.19 — admin 路径回归：完整原文（含表全名）保留。"""
    admin_token, _ = _login(client, "admin", "admin123")
    r = client.put(
        "/api/admin/catalog",
        json={"lexicon": {"用户": ["app.users"]}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    conv_id = _create_conv_with_message(
        client, admin_token,
        explanation="基于 app.users 查询",
        db_error="Table app.users not found",
    )

    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    msg = r.json()[-1]
    # admin 视图保留原文
    assert "app.users" in msg["explanation"]
    assert "app.users" in msg["db_error"]


def test_v060019_non_admin_fail_open_when_lexicon_empty(client):
    """v0.6.0.19 — lexicon 缺失场景：analyst 看到原文（fail-open 不阻塞）。"""
    admin_token, _ = _login(client, "admin", "admin123")
    # 清空 lexicon
    r = client.put(
        "/api/admin/catalog",
        json={"lexicon": {}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    import time
    uname = f"biz_v19_c_{int(time.time() * 1000)}"
    r = client.post(
        "/api/admin/users",
        json={"username": uname, "password": "test12345", "display_name": "Biz V19 C", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), r.text

    user_token, _ = _login(client, uname, "test12345")
    conv_id = _create_conv_with_message(
        client, user_token,
        explanation="基于 some.table 查询",
    )

    r = client.get(f"/api/conversations/{conv_id}/messages",
                   headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    msg = r.json()[-1]
    # fail-open：未替换原文
    assert "some.table" in msg["explanation"]
