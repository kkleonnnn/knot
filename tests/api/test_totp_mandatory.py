"""v0.6.5.0 — 强制 2FA 守护测试（admin 不豁免 + 默认 on + 应急后门）.

R-2FA-1  admin 与普通用户一致强制 enroll（删 v0.6.2.0 R-PB-B1-3 bootstrap bypass 优先级 2）
R-2FA-2  KNOT_TOTP_REQUIRED 默认 on（unset → 强制）；显式 =false opt-out（eval/demo）
R-2FA-3  KNOT_TOTP_BYPASS_ADMIN=true 应急后门（唯一豁免路径）
R-2FA-5  /api/totp/* 白名单可达（强制 ≠ 锁死）+ 已 enroll 用户通过 gate

守护者 Stage 3 C3：default-on 测试用 `monkeypatch.delenv` 揭真 default —— conftest autouse
设 KNOT_TOTP_REQUIRED=false 隔离全套；若守护测试用 setenv("true") 仅测显式 true 路径，
会漏验「default 翻转（getenv 默认 ""→"true"）」本身 → 回归洞。delenv 先例 = R-37 master key。
"""
import pyotp

# 受保护非白名单端点（既非 /api/totp/* 也非 /api/auth/*）
_PROTECTED = "/api/conversations"


def _enroll_admin(client, auth_headers):
    """走 /api/totp/* 白名单完成 admin enroll（强制态下仍可达 — R-2FA-5）。"""
    init = client.post("/api/totp/enroll-init", headers=auth_headers).json()
    code = pyotp.TOTP(init["secret"]).now()
    r = client.post("/api/totp/enroll-complete", headers=auth_headers,
                    json={"secret": init["secret"], "code": code})
    assert r.status_code == 200, f"enroll-complete failed: {r.text}"


def test_R_2FA_2_default_on_forces_unenrolled(client, auth_headers, monkeypatch):
    """R-2FA-2：默认 on —— unset KNOT_TOTP_REQUIRED → 未 enroll 用户受保护端点 403.

    delenv 揭真 default（守护者 C3）：验 default 翻转本身，非显式 true 路径。
    """
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get(_PROTECTED, headers=auth_headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "totp_enroll_required"


def test_R_2FA_1_admin_not_bootstrap_bypassed(client, auth_headers, monkeypatch):
    """R-2FA-1：admin 不再享 0-admin bootstrap bypass（删优先级 2）.

    旧 v0.6.2.0 行为 = 0 admin enrolled → admin 被自动放行；本测试断言新行为 = 403。
    fresh tmp DB 仅 seed admin（未 enroll）→ 0 admin enrolled → 旧 bootstrap 会放行 admin。
    """
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get(_PROTECTED, headers=auth_headers)
    assert r.status_code == 403, "admin 应被强制 enroll（bootstrap bypass 已删）"
    assert r.json()["detail"] == "totp_enroll_required"


def test_R_2FA_3_emergency_backdoor_bypasses_admin(client, auth_headers, monkeypatch):
    """R-2FA-3：KNOT_TOTP_BYPASS_ADMIN=true → admin 应急豁免（唯一后门，防永久锁死）."""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)  # 默认 on
    monkeypatch.setenv("KNOT_TOTP_BYPASS_ADMIN", "true")
    r = client.get(_PROTECTED, headers=auth_headers)
    assert r.status_code == 200, "应急后门应放行 admin"


def test_R_2FA_2_optout_false_disables(client, auth_headers, monkeypatch):
    """R-2FA-2：显式 KNOT_TOTP_REQUIRED=false → 关闭强制（eval/demo 快速评估）."""
    monkeypatch.setenv("KNOT_TOTP_REQUIRED", "false")
    r = client.get(_PROTECTED, headers=auth_headers)
    assert r.status_code == 200, "opt-out=false 应关闭强制"


def test_R_2FA_5_enrolled_passes_gate(client, auth_headers, monkeypatch):
    """R-2FA-5：已 enroll 用户在强制态下通过 gate（白名单 enroll 可达 → 强制 ≠ 锁死）.

    先经 /api/totp/* 白名单完成 enroll（强制态下仍可达），再验受保护端点 200。
    """
    _enroll_admin(client, auth_headers)
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)  # 默认 on
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get(_PROTECTED, headers=auth_headers)
    assert r.status_code == 200, "已 enroll 用户应通过 gate"
