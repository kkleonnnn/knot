"""tests/services/test_audit_v2_pii — v0.6.3.0 段 5 B2 audit V2 commit 2 守护测试。

R-PB-B2-补2（R-62 同步偿还）：v0.6.2.0 给 user_repo._USER_ENCRYPTED_COLS 加 totp_secret 时
漏同步 audit_service._PII_BLACKLIST（破 R-62）→ 本 PATCH 补 totp_secret + recovery_code + secret。

覆盖：
- R-62 同步断言：_PII_BLACKLIST ⊇ _USER_ENCRYPTED_COLS（防未来再漏）
- _scrub redact totp_secret / recovery_code / secret（R-PB-B2-补2 偿还生效）
- 6 audit_action detail PII：context_violation int 标量不误 redact + 敏感字段名 redact（B2.1）
"""
from knot.repositories.user_repo import _USER_ENCRYPTED_COLS
from knot.services.audit_service import _PII_BLACKLIST, _REDACTED, _scrub


# ─── R-PB-B2-补2 R-62 同步偿还 ────────────────────────────────────────

def test_pii_blacklist_superset_user_encrypted_cols():
    """R-62 同步断言：_PII_BLACKLIST ⊇ _USER_ENCRYPTED_COLS（含 totp_secret）— 防未来再漏。"""
    missing = set(_USER_ENCRYPTED_COLS) - _PII_BLACKLIST
    assert not missing, f"R-62 违规：_USER_ENCRYPTED_COLS 这些字段未在 _PII_BLACKLIST：{missing}"


def test_pii_blacklist_has_totp_secret():
    """R-PB-B2-补2：totp_secret 在 _PII_BLACKLIST（v0.6.2.0 漏同步偿还）。"""
    assert "totp_secret" in _PII_BLACKLIST
    assert "recovery_code" in _PII_BLACKLIST
    assert "secret" in _PII_BLACKLIST


def test_scrub_redacts_totp_secret():
    """_scrub redact totp_secret（偿还生效 — 未来 audit detail 含 totp_secret 被 redact）。"""
    out = _scrub({"totp_secret": "enc_v1:abc", "operator_id": 5})
    assert out["totp_secret"] == _REDACTED
    assert out["operator_id"] == 5  # 非敏感字段保留


def test_scrub_redacts_recovery_and_secret():
    out = _scrub({"recovery_code": "AAAA-BBBB", "secret": "JBSWY3DP", "phase": "login"})
    assert out["recovery_code"] == _REDACTED
    assert out["secret"] == _REDACTED
    assert out["phase"] == "login"  # 非敏感保留


# ─── B2.1 6 audit_action detail PII（context_violation int 标量不误 redact）──

def test_scrub_context_violation_detail_int_preserved():
    """catalog.context_violation detail {attempted/expected: int} 标量不误 redact（非敏感字段名）。"""
    out = _scrub({"attempted_catalog_id": 1, "expected_catalog_id": 5})
    assert out["attempted_catalog_id"] == 1
    assert out["expected_catalog_id"] == 5


def test_scrub_verify_failed_detail_schema_preserved():
    """远古补3 verify_failed detail {phase, recovery} 标量不误 redact。"""
    out = _scrub({"phase": "login", "recovery": True})
    assert out["phase"] == "login"
    assert out["recovery"] is True
