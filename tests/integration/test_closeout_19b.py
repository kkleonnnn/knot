"""v0.8.20 19b — F4（2 SSRF）+ F6a（SSE 中断成本落账）集成测。"""
from __future__ import annotations


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_F4_db_test_requires_admin(client, auth_headers):
    """db/test 从 get_current_user 收紧为 require_tenant_admin：非 admin analyst → 403。"""
    # admin 建一个 analyst
    client.post("/api/admin/users", json={"username": "an1", "password": "pw12345", "role": "analyst"},
                headers=auth_headers)
    an_token = _login(client, "an1", "pw12345")
    r = client.post("/api/db/test",
                    json={"db_host": "10.0.0.5", "db_port": 3306, "db_user": "x",
                          "db_password": "y", "db_database": "z"},
                    headers={"Authorization": f"Bearer {an_token}"})
    assert r.status_code == 403, f"非 admin 应 403（SSRF 收紧），实际 {r.status_code}: {r.text[:200]}"


def test_F4_datasource_http_base_url_allowlist(client, auth_headers, monkeypatch):
    """创建 http 数据源时 base_url 不在 egress allowlist → 400（防存任意内网 endpoint）。"""
    import json as _json
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "api.allowed.example.com")
    body = {
        "name": "evil-http", "description": "", "db_host": "", "db_port": 0,
        "db_user": "", "db_password": "", "db_database": "", "db_type": "http",
        "http_config": _json.dumps({"base_url": "http://10.0.0.9:8080", "auth_value": "t"}),
    }
    r = client.post("/api/admin/datasources", json=body, headers=auth_headers)
    assert r.status_code == 400, f"内网 base_url 应被 allowlist 拒 400，实际 {r.status_code}: {r.text[:200]}"


def test_F6a_sse_interrupt_records_incurred_cost(client, auth_headers, monkeypatch):
    """SSE 中途抛 KnotError → 已发生的 clarifier 成本经 _flush_interrupt_cost 落账（monthly_cost_usd 增）。"""
    from knot.api import query as query_module
    from knot.models.errors import KnotError
    from knot.repositories import user_repo
    from knot.services import cost_service

    monkeypatch.setattr(query_module, "get_user_engine", lambda u: (object(), "## t\n- c INT"))

    async def _fake_clarifier(*a, **k):
        buckets = k.get("agent_buckets") or a[-1]
        cost_service.add_agent_cost(buckets, "clarifier", 0.00234, 100, 50)
        return {"is_clear": True, "clarification_question": "", "refined_question": "q",
                "analysis_approach": "", "intent": "query", "input_tokens": 100, "output_tokens": 50}
    monkeypatch.setattr(query_module.query_steps, "run_clarifier_step", _fake_clarifier)

    # select_agent_key 第 1 次调用（clarifier key）放行 → clarifier 跑 + 加成本；第 2 次（sql_planner key）
    # 抛 KnotError → 走 generate() 通用 except → _flush_interrupt_cost（此时 buckets 已有 clarifier 成本）。
    orig_sel = query_module.query_steps.select_agent_key
    st = {"n": 0}

    def _sel(*a, **k):
        st["n"] += 1
        if st["n"] >= 2:
            raise KnotError("boom mid-pipeline")
        return orig_sel(*a, **k)
    monkeypatch.setattr(query_module.query_steps, "select_agent_key", _sel)

    before = user_repo.get_user_by_username("admin").get("monthly_cost_usd") or 0

    conv = client.post("/api/conversations", json={"title": "f6a"}, headers=auth_headers)
    cid = conv.json()["id"]
    r = client.post(f"/api/conversations/{cid}/query-stream",
                    json={"question": "q", "use_agent": False}, headers=auth_headers)
    assert r.status_code == 200
    after = user_repo.get_user_by_username("admin").get("monthly_cost_usd") or 0
    assert after > before, f"中断应落账已发生 clarifier 成本（F6a）：before={before} after={after}"
