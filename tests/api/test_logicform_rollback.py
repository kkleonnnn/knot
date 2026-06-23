"""tests/api/test_logicform_rollback.py — v0.7.6 C1 LogicForm append-only 恢复守护。

R-SL-57 gate + R-2FA carrier / R-SL-58 append-only（0 删 / 0 改历史）/ R-SL-59 logicform.rollback audit /
R-SL-60 byte-equal 复制源 + restored_from_audit_id / R-SL-61 不回流（0 metric 口径写）/ 404。

恢复 = 用源版本 LF **忠实字节复制**新建修正行（is_corrected=1, restored_from_audit_id=源 id）；链尾=当前采纳。
"""
from knot.repositories import (
    audit_repo,
    conversation_repo,
    message_repo,
    metric_repo,
    semantic_audit_repo,
    user_repo,
)


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


def _seed_message():
    admin_id = user_repo.get_user_by_username("admin")["id"]
    cid = conversation_repo.create_conversation(admin_id)
    return message_repo.save_message(cid, "原问题", "SELECT 1", "", "high", [], "", 0.0, 0, 0, 0)


# ─── R-SL-57 gate + R-2FA carrier + 404 ──────────────────────────────

def test_restore_requires_auth(client):
    r = client.post("/api/admin/logicform-audit/1/restore")
    assert r.status_code in (401, 403)


def test_restore_rejects_non_admin(client, auth_headers):
    client.post("/api/admin/users", json={"username": "rb_analyst", "password": "p", "role": "analyst"},
                headers=auth_headers)
    tok = client.post("/api/auth/login", json={"username": "rb_analyst", "password": "p"}).json()["token"]
    r = client.post("/api/admin/logicform-audit/1/restore", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403                               # 恢复仅 admin 面（脱敏 R-SL-64）


def test_restore_2fa_enroll_carrier(client, auth_headers, monkeypatch):
    """R-SL-57 R-2FA 正向 carrier：default-on + 未 enroll admin → 403 totp_enroll_required（仿 v0.7.2 R-SL-6）。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.post("/api/admin/logicform-audit/1/restore", headers=auth_headers)
    assert r.status_code == 403 and r.json()["detail"] == "totp_enroll_required"


def test_restore_404_unknown_audit(client, auth_headers):
    r = client.post("/api/admin/logicform-audit/99999/restore", headers=auth_headers)
    assert r.status_code == 404


# ─── R-SL-58 append-only + R-SL-60 byte-equal 复制 + R-SL-59 audit（守护者聚焦）───

def test_restore_append_only_byte_equal_copy_and_audit(client, auth_headers):
    mid = _seed_message()
    src = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1,
                                           logicform_json='{"metrics":["gmv"],"dimensions":["region"]}')
    before = semantic_audit_repo.list_by_message(mid)
    r = client.post(f"/api/admin/logicform-audit/{src}/restore", headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    after = semantic_audit_repo.list_by_message(mid)

    assert len(after) == len(before) + 1                           # R-SL-58 append（+1 行）
    src_row = next(x for x in after if x["id"] == src)
    assert src_row == next(x for x in before if x["id"] == src)    # R-SL-58 源行 byte-equal 不变（0 改）
    new_row = after[-1]                                            # 链尾 = 恢复行（id 最大）
    assert new_row["logicform_json"] == src_row["logicform_json"]  # R-SL-60 忠实字节复制
    assert new_row["compile_error_reason"] == src_row["compile_error_reason"]
    assert new_row["restored_from_audit_id"] == src                # R-SL-60 来源标记
    assert new_row["is_corrected"] == 1 and new_row["parent_message_id"] == mid
    assert _last_action("logicform.rollback") is not None          # R-SL-59 mutation 留痕


def test_restore_near_miss_faithful_copy(client, auth_headers):
    """R-SL-60 / D4：恢复 near-miss 源 → 恢复行 compile_error_reason 忠实复制（非重新判定，0 重编译）。"""
    mid = _seed_message()
    src = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1,
                                           logicform_json='{"metrics":["gmv"]}',
                                           compile_error_reason="维度归属歧义→回退")
    client.post(f"/api/admin/logicform-audit/{src}/restore", headers=auth_headers)
    new_row = semantic_audit_repo.list_by_message(mid)[-1]
    assert new_row["compile_error_reason"] == "维度归属歧义→回退"     # near-miss 状态忠实复制


# ─── R-SL-61 诚实边界：恢复不回流（不改 metric 口径）──────────────────────

def test_restore_does_not_mutate_metric_caliber(client, auth_headers):
    """R-SL-61：恢复**不改 metric 口径**（侧表不回流查询路径）—— metrics 表 0 变更。"""
    mid = _seed_message()
    src = semantic_audit_repo.create_audit(message_id=mid, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    before = len(metric_repo.list_metrics())
    client.post(f"/api/admin/logicform-audit/{src}/restore", headers=auth_headers)
    assert len(metric_repo.list_metrics()) == before               # 口径单一真源 metrics 表不变（不回流）
