"""tests/api/test_query_live_desensitize.py — v0.7.35（B1.2）实时查询路径脱敏守护。

对抗 review（Stage-2/3-等效）抓到的**同步 /query 端点旁路**（R-B1.2-8）：
use_agent=true 时 POST /query 曾返 raw agent_steps（thought/action/observation 含库表名）
+ raw sql/error 给非 admin，0 gate = 绕过整个 SSE 脱敏。本文件守护该端点非 admin 脱敏 +
admin 原样（byte-equal）回归。

（SSE query-stream 路径复用同一 scrub_query_payload — 单元覆盖见
 tests/services/test_scrub_query_payload.py；live SSE 端到端由 kk 手测锚点验证。）
"""
from __future__ import annotations

import time


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _set_lexicon(client, admin_token, lexicon):
    r = client.put("/api/admin/catalog", json={"lexicon": lexicon},
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text


def _make_analyst(client, admin_token, tag):
    uname = f"biz_b12_{tag}_{int(time.time() * 1000)}"
    r = client.post("/api/admin/users",
                    json={"username": uname, "password": "test12345",
                          "display_name": "B12", "role": "analyst"},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code in (200, 201), r.text
    return _login(client, uname, "test12345")


class _FakeResult:
    """伪 AgentResult：含库表名的 sql / explanation / error（success=False → error 落地）。"""
    sql = "SELECT * FROM dwd_user_deal WHERE dt='2026-01-01'"
    rows = [{"x": 1}]
    explanation = "查询 dwd_user_deal 完成"
    confidence = "high"
    error = "Table dwd_user_deal locked"
    success = False
    total_input_tokens = 10
    total_output_tokens = 20


_FAKE_STEPS = [{"step": 1, "thought": "查 dwd_user_deal", "action": "run_sql",
                "observation": "SELECT * FROM dwd_user_deal"}]


def _patch_pipeline(monkeypatch):
    """绕过 doris + LLM：假 engine + 假 run_agent_step_sync（返 sql + agent_steps 含库表名）。"""
    from knot.api import query as query_module
    monkeypatch.setattr(query_module, "get_user_engine",
                        lambda u: (object(), "## dwd_user_deal\n- col INT"))
    monkeypatch.setattr(query_module.query_steps, "run_agent_step_sync",
                        lambda *a, **k: (_FakeResult(), list(_FAKE_STEPS)))


def test_sync_query_non_admin_scrubbed(client, monkeypatch):
    """R-B1.2-8：非 admin 同步 /query use_agent=true → agent_steps suppress + sql pop +
    error/explanation 表名脱敏。"""
    admin_token, _ = _login(client, "admin", "admin123")
    _set_lexicon(client, admin_token, {"用户交易": ["dwd_user_deal"]})
    user_token, user = _make_analyst(client, admin_token, "na")
    assert user["role"] == "analyst"
    _patch_pipeline(monkeypatch)

    conv = client.post("/api/conversations", json={"title": "b12"},
                       headers={"Authorization": f"Bearer {user_token}"})
    cid = conv.json()["id"]
    r = client.post(f"/api/conversations/{cid}/query",
                    json={"question": "q", "use_agent": True},
                    headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_steps"] == [], f"非 admin agent_steps 应 suppress；实际 {body['agent_steps']}"
    assert "sql" not in body, f"非 admin sql 应删；keys={list(body.keys())}"
    assert "dwd_user_deal" not in body["error"], f"未脱敏 error：{body['error']}"
    assert "用户交易" in body["error"]
    assert "dwd_user_deal" not in body["explanation"], f"未脱敏 explanation：{body['explanation']}"


def test_sync_query_admin_unchanged(client, auth_headers, monkeypatch):
    """admin 同步 /query：agent_steps + sql 原样保留（byte-equal，脱敏 0 改动 R-脱敏-3）。"""
    _patch_pipeline(monkeypatch)
    conv = client.post("/api/conversations", json={"title": "b12-admin"}, headers=auth_headers)
    cid = conv.json()["id"]
    r = client.post(f"/api/conversations/{cid}/query",
                    json={"question": "q", "use_agent": True},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_steps"] == _FAKE_STEPS, "admin agent_steps 应原样保留"
    assert body["sql"] == _FakeResult.sql, "admin sql 应原样保留"
    assert body["error"] == _FakeResult.error, "admin error 原文（含库表名）"
