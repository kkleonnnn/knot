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


# ─── v0.6.5.1 review 跟进：非 admin 安全边界（#153 复审 🔴 + 🟢）─────────

def _make_analyst(client, auth_headers):
    """admin API 建 analyst + 拿 token（2FA 仍 off 时 setup 调）。

    守护者 Stage 3 C1：admin 建的用户默认 must_change_password=0（schema.sql DEFAULT 0；
    create_user 不设它 — 仅 seed admin 特例 =1）。仍防御性清除（防 schema 默认未来变）；
    真守护 = 断言 detail=="totp_enroll_required"（非泛型 403 — 改密 gate 先于 TOTP gate）。
    """
    r = client.post("/api/admin/users", headers=auth_headers,
                    json={"username": "analyst1", "password": "analystpass123", "role": "analyst"})
    assert r.status_code == 200, f"create analyst failed: {r.text}"
    from knot.repositories import user_repo
    u = user_repo.get_user_by_username("analyst1")
    if u and u.get("must_change_password"):
        user_repo.update_user(u["id"], must_change_password=0)  # 防御性（默认已 0）
    login = client.post("/api/auth/login", json={"username": "analyst1", "password": "analystpass123"})
    assert login.status_code == 200, f"analyst login failed: {login.text}"
    return {"Authorization": f"Bearer {login.json()['token']}"}


def test_R_2FA_3_backdoor_does_not_leak_to_nonadmin(client, auth_headers, monkeypatch):
    """🔴 后门 admin-only：非 admin + KNOT_TOTP_BYPASS_ADMIN=true → 仍 403（后门不泄漏）.

    回归守护 C1（保 role 检查）：gate `role=="admin" and _admin_bypass_active()` 对非 admin
    短路 → 强制。若有人删 role 检查（`if not _admin_bypass_active()`）→ analyst 错误豁免 → 本测试红。
    """
    analyst = _make_analyst(client, auth_headers)
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)   # 默认 on
    monkeypatch.setenv("KNOT_TOTP_BYPASS_ADMIN", "true")      # 后门仅 admin
    r = client.get(_PROTECTED, headers=analyst)
    assert r.status_code == 403, "非 admin 不享应急后门"
    assert r.json()["detail"] == "totp_enroll_required"       # 非泛型 403（守护者 C1）


def test_R_2FA_1_nonadmin_forced_enroll(client, auth_headers, monkeypatch):
    """🟢 非 admin 默认 on 被强制 enroll（无 bootstrap 豁免，本就强制）."""
    analyst = _make_analyst(client, auth_headers)
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)   # 默认 on
    monkeypatch.delenv("KNOT_TOTP_BYPASS_ADMIN", raising=False)
    r = client.get(_PROTECTED, headers=analyst)
    assert r.status_code == 403
    assert r.json()["detail"] == "totp_enroll_required"       # 非泛型 403（守护者 C1）
