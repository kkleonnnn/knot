"""v0.6.5.2 F4-back — 2FA rollout 一次性 session 失效守护测试.

R-2FA 不变量：「运维更新后全员重新登录，登录后再绑定」—— 机制 = 启动期幂等 bump
全员 token_version → 旧 JWT 立即 401 JWT_REVOKED → 前端 401 拦截器清 token 重登。

守护者 Stage 3 C3 + F4-1：default-on 行为用 monkeypatch.delenv 揭真默认
（conftest 模块级 setdefault KNOT_TOTP_REQUIRED=false 使 import 时 rollout 确定性 skip）。
"""
import pytest


@pytest.fixture(autouse=True)
def _clear_token_version_cache():
    """防 token_version cache 跨测试泄露（admin_token 登录会缓存 ver）。"""
    from knot.services import totp_service
    totp_service._TOKEN_VERSION_CACHE.clear()
    yield
    totp_service._TOKEN_VERSION_CACHE.clear()


def test_F4back_rollout_bumps_all_when_default_on(client, monkeypatch):
    """(a) default-on（delenv）+ flag 未设 → bump 全员 token_version +1 + 落 flag + 返 bumped。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)  # 揭真 default-on
    from knot.repositories import settings_repo, user_repo
    from knot.services import totp_service

    before = user_repo.get_token_version(1)
    result = totp_service.apply_rollout_session_invalidation()

    assert result.get("bumped", 0) >= 1, f"应 bump ≥1 行；实际 {result}"
    assert user_repo.get_token_version(1) == before + 1, "admin token_version 应 +1"
    assert settings_repo.get_app_setting("totp_rollout_session_invalidated"), \
        "rollout flag 应已落 app_settings（时间戳）"


def test_F4back_rollout_idempotent(client, monkeypatch):
    """(b) 幂等：二次调用返 already_applied + token_version 不再变（不会每次重启踢人）。"""
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    from knot.repositories import user_repo
    from knot.services import totp_service

    first = totp_service.apply_rollout_session_invalidation()
    assert "bumped" in first
    ver_after_first = user_repo.get_token_version(1)

    second = totp_service.apply_rollout_session_invalidation()
    assert second == {"skipped": "already_applied"}, f"二次应 skip；实际 {second}"
    assert user_repo.get_token_version(1) == ver_after_first, "幂等：二次不应再 bump"


def test_F4back_rollout_skipped_when_totp_off(client, monkeypatch):
    """(c) KNOT_TOTP_REQUIRED=false → skip totp_not_required + token_version 不变（测试隔离根据）。"""
    monkeypatch.setenv("KNOT_TOTP_REQUIRED", "false")
    from knot.repositories import user_repo
    from knot.services import totp_service

    before = user_repo.get_token_version(1)
    result = totp_service.apply_rollout_session_invalidation()

    assert result == {"skipped": "totp_not_required"}, f"off 应 skip；实际 {result}"
    assert user_repo.get_token_version(1) == before, "off 时不应 bump"


def test_F4back_old_jwt_401_after_rollout(client, auth_headers, monkeypatch):
    """(d) rollout bump 后旧 ver JWT 打受保护端点 → 401 JWT_REVOKED（重登链起点）。

    token_version 检查（deps.py:123-127）在 enroll-gate 之前 → me() 也 401（非 enroll 403）。
    """
    monkeypatch.delenv("KNOT_TOTP_REQUIRED", raising=False)
    from knot.services import totp_service

    # baseline：旧 token（ver=1）me() 正常 200（me 白名单豁免 enroll-gate）
    me0 = client.get("/api/auth/me", headers=auth_headers)
    assert me0.status_code == 200, f"bump 前旧 token 应 200；实际 {me0.status_code}"

    totp_service.apply_rollout_session_invalidation()  # bump → ver=2 + cache clear

    me1 = client.get("/api/auth/me", headers=auth_headers)
    assert me1.status_code == 401, f"bump 后旧 ver JWT 应 401 JWT_REVOKED；实际 {me1.status_code}"
    assert me1.json()["detail"] == "JWT_REVOKED"
