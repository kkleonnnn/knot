"""tests/api/test_logicform_history.py — v0.7.5 C1 LogicForm 版本历史守护（read-only）。

R-SL-49 gate + R-2FA carrier / R-SL-50 read-only（0 mutation）/ R-SL-51 分层（near-miss 显存 reason
**不重编译** + hit-now-fails 优雅）/ R-SL-53 时序 / R-SL-56 LogicForm 忠实回传（diff 主体）/ 404。

版本链 = message 全审计行（原始 is_corrected=0 + 修正 is_corrected=1）ORDER BY id。
"""
from knot.repositories import conversation_repo, message_repo, semantic_audit_repo, user_repo
from knot.services.semantic import compiler


def _seed_message():
    """admin 会话 + 真 message → 返 message_id（版本链挂载点）。"""
    admin_id = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(admin_id)
    return message_repo.save_message(cid, "原问题", "SELECT 1", "", "high", [], "", 0.0, 0, 0, 0)


# ─── R-SL-49 gate + R-2FA carrier + 404 ──────────────────────────────

def test_history_requires_auth(client):
    r = client.get("/api/admin/logicform-audit/1/history")
    assert r.status_code in (401, 403)


def test_history_rejects_non_admin(client, auth_headers):
    client.post("/api/admin/users", json={"username": "hist_analyst", "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "hist_analyst", "password": "p"}).json()["token"]
    r = client.get("/api/admin/logicform-audit/1/history", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403                               # LogicForm 历史仅 admin 面（脱敏 R-SL-52）


def test_history_2fa_enroll_carrier(client, auth_headers, monkeypatch):
    """R-SL-49 R-2FA 正向 carrier：default-on + 未 enroll admin → 403 totp_enroll_required（仿 v0.7.2 R-SL-6）。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get("/api/admin/logicform-audit/1/history", headers=auth_headers)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_required"


def test_history_404_unknown_audit(client, auth_headers):
    r = client.get("/api/admin/logicform-audit/99999/history", headers=auth_headers)
    assert r.status_code == 404


# ─── R-SL-53 时序 + R-SL-51 near-miss 不重编译（守护者聚焦）─────────────

def test_history_chain_order_and_near_miss_no_recompile(client, auth_headers, monkeypatch):
    """R-SL-53 版本链时序（id ASC）+ R-SL-51 near-miss **显存 reason 不重编译**（守护者 Stage 3 承重）。

    spy compile：near-miss 行不调 compile_logicform（历史真相）；hit 行才重编译。
    """
    mid = _seed_message()
    a_orig = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1,
                                              logicform_json='{"metrics":["gmv"]}',
                                              compile_error_reason="维度归属歧义→回退")          # 原始 near-miss
    a_corr = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1,
                                              logicform_json='{"metrics":["gmv"],"dimensions":["region"]}',
                                              is_corrected=1, parent_message_id=mid)             # 修正 hit
    calls = []
    monkeypatch.setattr(compiler, "compile_logicform",
                        lambda lf, cat, tc: calls.append(1) or "SELECT 1 AS x LIMIT 1")
    r = client.get(f"/api/admin/logicform-audit/{a_orig}/history", headers=auth_headers)
    assert r.status_code == 200
    vs = r.json()
    assert [v["audit_id"] for v in vs] == [a_orig, a_corr]            # R-SL-53 时序（id ASC，原始居首）
    assert vs[0]["kind"] == "near_miss" and vs[0]["reason"].startswith("维度")  # 原始：显存 reason
    assert vs[1]["kind"] == "hit" and vs[1]["sql"] == "SELECT 1 AS x LIMIT 1"    # 修正：当前重编译
    assert calls == [1]                                              # R-SL-51：仅 hit 重编译 1 次，near-miss 0
    assert all("logicform_json" in v for v in vs)                    # R-SL-56 忠实历史源回传（diff 主体）


def test_history_hit_recompile_failed_when_metric_missing(client, auth_headers):
    """R-SL-51 hit-now-fails：hit 行（reason 空）现重编译失败（测试 DB 无 metric → CompileError）→
    kind=hit_recompile_failed（与历史 near-miss 区分；保真度 R-SL-56 — 「当前编译失败」非历史真相）。"""
    mid = _seed_message()
    aid = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    r = client.get(f"/api/admin/logicform-audit/{aid}/history", headers=auth_headers)
    assert r.status_code == 200
    vs = r.json()
    assert vs[0]["kind"] == "hit_recompile_failed" and "metric" in vs[0]["reason"]   # 现失败（gmv 未定义）


# ─── R-SL-50 read-only（0 mutation）────────────────────────────────────

def test_history_read_only_no_mutation(client, auth_headers):
    """R-SL-50：/history 调用后 message 全版本链行数不变（read-only，0 新侧表行 / 0 新 message）。"""
    mid = _seed_message()
    semantic_audit_repo.create_audit(message_id=mid, catalog_id=1,
                                     logicform_json='{"metrics":["gmv"]}', compile_error_reason="x")
    before = len(semantic_audit_repo.list_by_message(mid))
    client.get(f"/api/admin/logicform-audit/{semantic_audit_repo.list_by_message(mid)[0]['id']}/history",
               headers=auth_headers)
    after = len(semantic_audit_repo.list_by_message(mid))
    assert after == before                                           # 0 新侧表行（read-only）
