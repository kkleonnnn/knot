"""tests/api/test_logicform_rerun.py — v0.7.4 C1 LogicForm 修正 re-run 真执行守护。

R-SL-41 gate + R-2FA carrier / R-SL-42 logicform.rerun audit（executed_sql 四元组）/
R-SL-43 containment 载体 = `_is_safe_sql`（注入 filter 经 execute_query 拒 + re-run 必经 execute_query 不裸连）/
R-SL-44 0 新 message 零污染 / R-SL-45 0 LLM / R-SL-47 D2-A 原用户 engine + 改源优雅 + 404。

re-run = 重编译（原 catalog R-SL-40）+ 原 message 用户 engine（D2-A）+ execute_query（DQL-only 收口）。
/correct 保持 compile-only（资深 v0.7.3 安全边界）；本端点独立 gate + 审计 + 真执行。
"""
from knot.adapters.db import doris
from knot.repositories import (
    audit_repo,
    conversation_repo,
    message_repo,
    semantic_audit_repo,
    user_repo,
)
from knot.services import cost_service
from knot.services.semantic import compiler


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


def _seed_audit(logicform_json: str = '{"metrics":["gmv"]}', catalog_id: int = 1):
    """建 admin 会话 + 真 message + 审计行 → 返 (audit_id, message_id, conv_id)；D2-A owner 可解析。"""
    admin_id = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(admin_id)
    mid = message_repo.save_message(cid, "原问题", "SELECT 1", "", "high", [], "", 0.0, 0, 0, 0)
    aid = semantic_audit_repo.create_audit(message_id=mid, catalog_id=catalog_id, logicform_json=logicform_json)
    return aid, mid, cid


# ─── R-SL-41 gate 鉴权 + R-2FA carrier ───────────────────────────────

def test_rerun_requires_auth(client):
    r = client.post("/api/admin/logicform-audit/1/rerun")
    assert r.status_code in (401, 403)                       # 无 token → 强制鉴权


def test_rerun_rejects_non_admin(client, auth_headers):
    client.post("/api/admin/users", json={"username": "rerun_analyst", "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "rerun_analyst", "password": "p"}).json()["token"]
    r = client.post("/api/admin/logicform-audit/1/rerun", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403                               # 非 admin → 403（真执行仅 admin 面）


def test_rerun_2fa_enroll_carrier(client, auth_headers, monkeypatch):
    """R-SL-41 R-2FA 正向 carrier：default-on + 未 enroll admin → 403 totp_enroll_required（仿 v0.7.2 R-SL-6）。

    gate 在 require_admin 依赖层先于 handler body 触发 → audit_id 不必存在。
    """
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.post("/api/admin/logicform-audit/1/rerun", headers=auth_headers)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_required"


def test_rerun_404_unknown_audit(client, auth_headers):
    r = client.post("/api/admin/logicform-audit/99999/rerun", headers=auth_headers)
    assert r.status_code == 404                               # 审计行不存在


# ─── R-SL-43 containment 载体 = _is_safe_sql（两段证明）──────────────────

def test_execute_query_is_dql_carrier_rejects_injection():
    """R-SL-43 ①载体：corrected LogicForm filters 裸进 WHERE（compiler.py:176 `where.append(str(f))`，无校验）
    → 注入 SQL 经 `execute_query` 顶部 `_is_safe_sql` 拒（单语句/DQL-only 收口，与 live 同源）。

    object() dummy engine 永不被 connect（_is_safe_sql 在 engine.connect 前拒）→ 安全可证非靠假设（CI sqlglot AST）。
    精确边界：containment = 只读单语句，非「限定 metric 范围」—— 任意只读子查询允许（admin 可信 + executed_sql 审计兜底）。
    """
    stacked_drop = "SELECT o.region FROM shop.orders o WHERE 1=1; DROP TABLE shop.orders LIMIT 200"
    rows, err = doris.execute_query(object(), stacked_drop)
    assert rows == [] and "安全检查未通过" in err               # 多语句 stacked → 拒（防注入）

    stacked_delete = "SELECT o.x FROM shop.orders o WHERE o.id > 0; DELETE FROM shop.orders LIMIT 200"
    rows2, err2 = doris.execute_query(object(), stacked_delete)
    assert rows2 == [] and "安全检查未通过" in err2              # 多语句 + DML → 拒


def test_rerun_routes_through_execute_query_not_raw(client, auth_headers, monkeypatch):
    """R-SL-43 ②路由：re-run **必经 `db_connector.execute_query`**（不裸连 conn.execute）→ 注入由 ①载体收口。
    同时验 R-SL-42（logicform.rerun audit + executed_sql）+ R-SL-45（0 LLM：cost_service 0 调用）。

    compile monkeypatch 为良性 SQL（真 compile 由 test_compiler 覆盖；本测试聚焦端点 → execute_query 管道）。
    """
    aid, mid, _cid = _seed_audit()
    calls = []
    cost_calls = []
    monkeypatch.setattr(compiler, "compile_logicform", lambda lf, cat, tc: "SELECT 1 AS x LIMIT 1")
    monkeypatch.setattr("knot.services.engine_cache.get_user_engine", lambda u: (object(), "schema"))
    monkeypatch.setattr(doris, "execute_query",
                        lambda eng, sql, **kw: (calls.append(sql) or [{"x": 1}], ""))
    monkeypatch.setattr(cost_service, "add_agent_cost",
                        lambda *a, **k: cost_calls.append(1))   # R-SL-45 spy：0 LLM 成本

    r = client.post(f"/api/admin/logicform-audit/{aid}/rerun", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["rows"] == [{"x": 1}] and body["row_count"] == 1
    assert calls == ["SELECT 1 AS x LIMIT 1"]                  # 必经 execute_query（compiled SQL 透传）
    assert cost_calls == []                                    # R-SL-45：0 LLM 成本桶
    act = _last_action("logicform.rerun")                     # R-SL-42：audit emit
    assert act is not None and "executed_sql" in (act.get("detail_json") or "")


# ─── R-SL-44 零污染 + R-SL-47 D2-A 原用户 engine 优雅降级 ─────────────────

def test_rerun_no_new_message_zero_pollution(client, auth_headers, monkeypatch):
    """R-SL-44：re-run 返 rows 临时，**0 新 message 写用户会话**（admin 动作不污染用户数据）。"""
    aid, _mid, cid = _seed_audit()
    monkeypatch.setattr(compiler, "compile_logicform", lambda lf, cat, tc: "SELECT 1 AS x LIMIT 1")
    monkeypatch.setattr("knot.services.engine_cache.get_user_engine", lambda u: (object(), "schema"))
    monkeypatch.setattr(doris, "execute_query", lambda eng, sql, **kw: ([{"x": 1}], ""))

    before = len(message_repo.get_messages(cid))
    client.post(f"/api/admin/logicform-audit/{aid}/rerun", headers=auth_headers)
    after = len(message_repo.get_messages(cid))
    assert after == before                                    # 0 新 message（零污染）


def test_rerun_original_user_engine_graceful_when_unavailable(client, auth_headers, monkeypatch):
    """R-SL-47 / D2-A：re-run 追溯**原 message 用户** engine（message→conv→user_id→get_user_engine）；
    admin seed 无数据源 → engine None → ok:False 优雅降级（改源/真空不崩，非安全问题）。

    compile monkeypatch 良性（隔离 engine 解析；真 compile 由 test_compiler 覆盖）→ 确保走到 get_user_engine
    （否则测试 DB 无 metric → compile 先失败返 compile_error，测不到 engine 分支）。
    """
    aid, _mid, _cid = _seed_audit()
    monkeypatch.setattr(compiler, "compile_logicform", lambda lf, cat, tc: "SELECT 1 AS x LIMIT 1")
    r = client.post(f"/api/admin/logicform-audit/{aid}/rerun", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "数据源" in body["error"]    # D2-A 链达 get_user_engine + 优雅
