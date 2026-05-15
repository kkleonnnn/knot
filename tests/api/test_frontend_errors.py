"""tests/api/test_frontend_errors.py — v0.6.0.4 F-B 前端错误上报守护。

覆盖：
- POST 落库成功 + 返回 id
- M-B2 PII 脱敏（手机 / 身份证 / 邮箱 / API key 模式）
- 长度硬截断（防 attacker stuff 超大 payload）
- admin GET 列表 + top_hashes 聚合
- 未登录 401
"""
from __future__ import annotations


def test_post_frontend_error_basic(client, auth_headers):
    r = client.post("/api/frontend-errors",
                    json={"message": "TypeError: undefined is not a function",
                          "stack": "at foo (app.js:42)\nat bar (app.js:10)",
                          "url": "https://app.example.com/page",
                          "error_hash": "abc123"},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["id"] > 0


def test_pii_redaction_phone_email_apikey(client, auth_headers):
    """M-B2 — message + stack 中的 PII 必须脱敏后落库。"""
    body = {
        "message": "Failed with phone 13812345678 / mail user@example.com / key sk-ant-api03-AAAAAAAAAAAAAAAAAAAAA",
        "stack": "at decrypt (enc_v1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA)",
        "url": "https://x/page?phone=18800000000",
        "error_hash": "h1",
    }
    client.post("/api/frontend-errors", json=body, headers=auth_headers)
    r = client.get("/api/admin/frontend-errors", headers=auth_headers)
    items = r.json()["items"]
    msg = items[0]["message"]
    stk = items[0]["stack"]
    assert "13812345678" not in msg, f"手机号未脱敏: {msg}"
    assert "user@example.com" not in msg, f"邮箱未脱敏: {msg}"
    assert "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAA" not in msg, f"API key 未脱敏: {msg}"
    assert "enc_v1:" not in stk or "<enc_v1>" in stk, f"Fernet 密文未脱敏: {stk}"
    assert "<phone>" in msg and "<email>" in msg and "<api_key>" in msg


def test_admin_list_with_top_hashes(client, auth_headers):
    """admin GET 返回 items + total + top_hashes 聚合。"""
    for i in range(3):
        client.post("/api/frontend-errors",
                    json={"message": f"err {i}", "stack": "", "url": "/", "error_hash": "freq1"},
                    headers=auth_headers)
    client.post("/api/frontend-errors",
                json={"message": "rare", "stack": "", "url": "/", "error_hash": "rare1"},
                headers=auth_headers)
    r = client.get("/api/admin/frontend-errors", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 4
    assert "top_hashes" in body
    # freq1 应排首位
    if body["top_hashes"]:
        assert body["top_hashes"][0]["error_hash"] == "freq1"
        assert body["top_hashes"][0]["cnt"] >= 3


def test_length_cap_prevents_payload_attack(client, auth_headers):
    """消息超 2000 字符 → Pydantic 422 拒收。"""
    huge = "X" * 3000
    r = client.post("/api/frontend-errors",
                    json={"message": huge, "stack": "", "url": "/", "error_hash": "h"},
                    headers=auth_headers)
    assert r.status_code == 422


def test_post_requires_auth(client):
    r = client.post("/api/frontend-errors",
                    json={"message": "x", "stack": "", "url": "/", "error_hash": "h"})
    assert r.status_code in (401, 403)


def test_admin_get_requires_admin(client):
    r = client.get("/api/admin/frontend-errors")
    assert r.status_code in (401, 403)
