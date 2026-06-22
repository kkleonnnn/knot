"""tests/api/test_logicform_audit_admin.py — v0.7.3 C2 审计 + C3 修正 admin 路由守护。

C2 gate 鉴权 + R-2FA carrier（非 admin 403 / 未 enroll admin 403）+ 命中/near-miss enrich。
C3 修正：重编译（原 catalog R-SL-40）+ 审计血缘（is_corrected/parent）+ logicform.correct audit；编译失败 ok:False。
LogicForm/SQL 仅 admin 面（脱敏链 sustained）。
"""
from knot.repositories import audit_repo, semantic_audit_repo


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


# ─── gate 鉴权 + R-2FA carrier ───────────────────────────────────────

def test_logicform_audit_requires_auth(client):
    r = client.get("/api/admin/logicform-audit")
    assert r.status_code in (401, 403)                       # 无 token → 强制鉴权


def test_logicform_audit_rejects_non_admin(client, auth_headers):
    client.post("/api/admin/users", json={"username": "lf_analyst", "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "lf_analyst", "password": "p"}).json()["token"]
    r = client.get("/api/admin/logicform-audit", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403                              # 非 admin → 403（LogicForm 仅 admin 面）


def test_logicform_audit_2fa_enroll_carrier(client, auth_headers, monkeypatch):
    """R-2FA 正向 carrier：default-on + 未 enroll admin → 403 totp_enroll_required（复用 test_totp_mandatory 模式）。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get("/api/admin/logicform-audit", headers=auth_headers)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_required"


# ─── 命中 / near-miss enrich ─────────────────────────────────────────

def test_logicform_audit_lists_hit_and_near_miss(client, auth_headers):
    semantic_audit_repo.create_audit(message_id=1, catalog_id=1,
                                     logicform_json='{"metrics":["gmv"]}')                  # 命中
    semantic_audit_repo.create_audit(message_id=2, catalog_id=1,
                                     logicform_json='{"metrics":["gmv"],"dimensions":["region"]}',
                                     compile_error_reason="无唯一 JOIN 路径 → 回退")          # near-miss
    r = client.get("/api/admin/logicform-audit", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    by_msg = {row["message_id"]: row for row in rows}
    assert by_msg[1]["hit"] is True and by_msg[1]["compile_error_reason"] == ""             # 命中
    assert by_msg[2]["hit"] is False and by_msg[2]["compile_error_reason"].startswith("无唯一")  # near-miss
    assert "logicform_json" in by_msg[1] and "question" in by_msg[1]                        # enrich 字段在


def test_logicform_audit_catalog_isolation(client, auth_headers):
    semantic_audit_repo.create_audit(message_id=1, catalog_id=1, logicform_json="a")
    semantic_audit_repo.create_audit(message_id=2, catalog_id=2, logicform_json="b")
    r = client.get("/api/admin/logicform-audit?catalog_id=1", headers=auth_headers)
    assert r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["message_id"] == 1   # R-SL-39/40 隔离


# ─── C3 修正（重编译 + 审计血缘 + logicform.correct audit）────────────

def test_correct_rejects_non_admin(client, auth_headers):
    aid = semantic_audit_repo.create_audit(message_id=1, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    client.post("/api/admin/users", json={"username": "lf_a2", "password": "p", "role": "analyst"}, headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "lf_a2", "password": "p"}).json()["token"]
    r = client.post(f"/api/admin/logicform-audit/{aid}/correct", json={"logicform": {"metrics": ["gmv"]}},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403                                  # 非 admin → 403


def test_correct_missing_audit_404(client, auth_headers):
    r = client.post("/api/admin/logicform-audit/99999/correct", json={"logicform": {"metrics": ["gmv"]}},
                    headers=auth_headers)
    assert r.status_code == 404


def test_correct_compile_fail_returns_not_ok(client, auth_headers):
    """修正后引用未定义 metric → 编译失败 → ok:False（不落血缘，admin 再调）。"""
    aid = semantic_audit_repo.create_audit(message_id=1, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    r = client.post(f"/api/admin/logicform-audit/{aid}/correct",
                    json={"logicform": {"metrics": ["nonexistent"]}}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is False and "compile_error" in r.json()


def test_correct_recompiles_and_audits(client, auth_headers, monkeypatch):
    """修正命中：原 catalog 重编译（R-SL-40）→ ok:True + sql + 审计血缘行（is_corrected）+ logicform.correct audit。"""
    from knot.repositories import metric_repo
    from knot.services import query_helper
    metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)", base_object="shop.orders", dimensions="[]")
    monkeypatch.setattr(query_helper, "_parse_catalog_content",  # R-SL-40 原 catalog（带 orders 物理表）
                        lambda row: {"catalog_id": 1, "tables": [{"db": "shop", "table": "orders", "source_type": "db"}], "relations": []})
    aid = semantic_audit_repo.create_audit(message_id=5, catalog_id=1, logicform_json='{"metrics":["gmv"],"dimensions":["x"]}')
    r = client.post(f"/api/admin/logicform-audit/{aid}/correct",
                    json={"logicform": {"metrics": ["gmv"]}}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "SUM(o.amt) AS gmv" in r.json()["sql"]                # 重编译确定性 SQL
    new = semantic_audit_repo.get_audit(r.json()["audit_id"])
    assert new["is_corrected"] == 1 and new["parent_message_id"] == 5   # 审计血缘
    assert _last_action("logicform.correct") is not None        # R-SL-38 治理 audit
