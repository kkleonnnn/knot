"""tests/api/test_logicform_audit_admin.py — v0.7.3 C2 LogicForm 审计 admin 路由守护。

gate 鉴权 + R-2FA carrier（非 admin 403 / 未 enroll admin 403 totp_enroll_required）+ 命中/near-miss enrich。
LogicForm/SQL 仅 admin 面（脱敏链 sustained）。
"""
from knot.repositories import semantic_audit_repo


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
