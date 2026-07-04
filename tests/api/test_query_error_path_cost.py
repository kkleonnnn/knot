"""tests/api/test_query_error_path_cost.py — v0.7.39（B3.2）错误路径 cost 记账守护。

回归守护 B3.2 latent bug：query_stream 的错误早退分支（跨源 JOIN 守护 / HTTP 失败）
曾 save_message(cost_usd=0) 且无 update_user_usage → clarifier 已发生的 LLM 成本被丢弃
（message 记 0 + 用户用量/预算欠计）。修后镜像澄清早退（aggregate + kwargs + update_user_usage）。

本测试注入一笔 clarifier 桶成本 + 触发跨源守护，断言落库 message.cost_usd > 0（记了 clarifier 成本）。
（HTTP 失败分支同一修复模式；由 adversarial verify + 本测试代表覆盖。）
"""
from __future__ import annotations

import time


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def test_cross_source_error_records_clarifier_cost(client, monkeypatch):
    """R-B3.2：跨源守护错误路径 save_message 记 clarifier 已发生成本（非 0）+ 分桶落库。"""
    from knot.api import query as query_module
    from knot.services import cost_service, http_planner

    admin_token, _ = _login(client, "admin", "admin123")

    # 假 engine（绕过 doris setup）
    monkeypatch.setattr(query_module, "get_user_engine",
                        lambda u: (object(), "## t\n- c INT"))

    # 假 clarifier：注入一笔 clarifier 桶成本（0.001）+ 返 is_clear=True（进入 HTTP 路由判定）
    _CLAR_COST = 0.00123

    async def _fake_clarifier(*a, **k):
        buckets = k.get("agent_buckets") or a[-1]
        cost_service.add_agent_cost(buckets, "clarifier", _CLAR_COST, 100, 50)
        return {
            "is_clear": True, "clarification_question": "",
            "refined_question": "各交易对 GMV 和外部持仓",
            "analysis_approach": "跨源聚合",
            "intent": "compare", "input_tokens": 100, "output_tokens": 50,
        }
    monkeypatch.setattr(query_module.query_steps, "run_clarifier_step", _fake_clarifier)

    # pick_http_route → 触发跨源守护 raise
    def _raise_cross(*a, **k):
        raise http_planner.CrossSourceJoinNotSupported("跨源 JOIN：SQL 表 + HTTP 表")
    monkeypatch.setattr(http_planner, "pick_http_route", _raise_cross)

    conv = client.post("/api/conversations", json={"title": "b32-cost"},
                       headers={"Authorization": f"Bearer {admin_token}"})
    cid = conv.json()["id"]
    r = client.post(f"/api/conversations/{cid}/query-stream",
                    json={"question": "各交易对 GMV 和外部持仓", "use_agent": False},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    # SSE 应含 cross_source_unsupported final 事件
    assert "cross_source_unsupported" in r.text, f"未走跨源守护分支：{r.text[:300]}"

    # 落库 message 记了 clarifier 成本（修前 = 0）
    from knot.repositories import message_repo
    msgs = message_repo.get_messages(cid)
    msg = msgs[-1]
    assert msg["db_error"] == "cross_source_unsupported", f"非跨源错误行：{msg.get('db_error')}"
    assert abs(msg["cost_usd"] - _CLAR_COST) < 1e-9, \
        f"R-B3.2 回归：错误路径应记 clarifier 成本 {_CLAR_COST}，实际 {msg['cost_usd']}"
    # 分桶也落库（clarifier_cost 列）
    assert msg.get("clarifier_cost", 0) > 0, f"clarifier_cost 分桶未落库：{msg.get('clarifier_cost')}"
