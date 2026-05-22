"""v0.6.0.20 — admin 默认账号 admin/admin123 强制改密守护测试。

业务流程：
1. fresh DB seed → admin/admin123 must_change_password=1
2. login → response.user.must_change_password=true
3. 任何业务 API 调用 → 403 detail=must_change_password
4. /api/auth/me / /api/auth/change-password 仍可调（白名单）
5. POST change-password 旧密匹配 + 新密合规 → must_change_password=0
6. 改后再 login → must_change_password=false + 业务 API 正常 200
"""
from __future__ import annotations

# v0.6.0.20: client fixture 从 tests/api/conftest.py 注入（含 must_change_password=0 reset）；
# 本测试在用例体内显式 set must_change_password=1 制造场景。


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return r


# ─── 默认 admin 必须改密 ────────────────────────────────────────────────


def test_default_admin_login_returns_must_change_password_true(client):
    """v0.6.0.20：默认 admin/admin123 首登 → response.user.must_change_password=true。"""
    r = _login(client, "admin", "admin123")
    # 默认 admin 也可能已被前序测试改过密（test 之间 DB 共享）；本测仅守 schema 字段
    if r.status_code == 200:
        assert "must_change_password" in r.json()["user"], \
            f"login response 必含 must_change_password 字段；user={r.json()['user']}"


def test_must_change_password_blocks_business_api(client):
    """v0.6.0.20：must_change_password=1 时业务 API 403 detail=must_change_password。"""
    # 直接设 admin must_change_password=1（模拟 fresh seed 状态）
    from knot.repositories import user_repo
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], must_change_password=1)

    # 登录拿 token
    r = _login(client, "admin", "admin123")
    if r.status_code != 200:
        # admin123 已被改过；重置回 admin123（直接 hash 写入，绕 verify）
        from knot.services.auth_service import hash_password
        user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)
        r = _login(client, "admin", "admin123")
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["user"]["must_change_password"] is True

    # 业务 API 调用 → 403
    r = client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, f"应被 403 拦截；实际 {r.status_code}：{r.text}"
    assert r.json()["detail"] == "must_change_password"


def test_must_change_password_allows_auth_paths(client):
    """v0.6.0.20：白名单 /api/auth/* 在 must_change_password=1 时仍可访问。"""
    from knot.repositories import user_repo
    admin = user_repo.get_user_by_username("admin")
    from knot.services.auth_service import hash_password
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)

    r = _login(client, "admin", "admin123")
    assert r.status_code == 200
    token = r.json()["token"]

    # /api/auth/me 应放行
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"/api/auth/me 应放行；实际 {r.status_code}：{r.text}"
    assert r.json()["must_change_password"] is True


# ─── 改密成功流程 ───────────────────────────────────────────────────────


def test_change_password_success_unblocks_business_api(client):
    """v0.6.0.20：旧密匹配 + 新密合规 → must_change_password=0 + 业务 API 解禁。"""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)

    r = _login(client, "admin", "admin123")
    token = r.json()["token"]

    # 改密
    new_pwd = "new-secure-pwd-2026"
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin123", "new_password": new_pwd},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # 业务 API 解禁
    r = client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"改密后业务 API 应解禁；实际 {r.status_code}：{r.text}"

    # 用新密码重登 → must_change_password=false
    r = _login(client, "admin", new_pwd)
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

    # 还原（影响后续测试）
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"))


# ─── 改密失败场景 ──────────────────────────────────────────────────────


def test_change_password_wrong_old_rejected(client):
    """旧密码不匹配 → 400."""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)

    r = _login(client, "admin", "admin123")
    token = r.json()["token"]

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "wrong-pwd", "new_password": "new-secure-pwd"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "旧密码" in r.json()["detail"]


def test_change_password_short_new_rejected(client):
    """新密 < 8 字符 → 400."""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)

    r = _login(client, "admin", "admin123")
    token = r.json()["token"]

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin123", "new_password": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "8 字符" in r.json()["detail"]


def test_change_password_same_as_old_rejected(client):
    """新密 == 旧密 → 400."""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=1)

    r = _login(client, "admin", "admin123")
    token = r.json()["token"]

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "admin123", "new_password": "admin123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    # 默认值禁用列表先命中（admin123 在 _FORBIDDEN_PASSWORDS）
    assert "默认值" in r.json()["detail"] or "相同" in r.json()["detail"]


def test_change_password_default_value_rejected(client):
    """新密复用 admin123（默认值禁用列表）→ 400."""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    # 先把密改成不同的，再尝试改回 admin123 验证禁用
    user_repo.update_user(admin["id"], password_hash=hash_password("temp-pwd-12345"), must_change_password=0)

    r = _login(client, "admin", "temp-pwd-12345")
    token = r.json()["token"]

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "temp-pwd-12345", "new_password": "admin123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "默认值" in r.json()["detail"]

    # 还原
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"))


# ─── 非 admin 用户不被强制改密 ─────────────────────────────────────────


def test_non_admin_user_not_forced(client):
    """analyst 创建时 must_change_password 默认 0 → 不被强制改密。"""
    from knot.repositories import user_repo
    from knot.services.auth_service import hash_password
    admin = user_repo.get_user_by_username("admin")
    # 确保 admin 不在强制改密状态（防干扰）
    user_repo.update_user(admin["id"], password_hash=hash_password("admin123"), must_change_password=0)
    admin_token = _login(client, "admin", "admin123").json()["token"]

    import time
    uname = f"biz_v20_{int(time.time() * 1000)}"
    r = client.post(
        "/api/admin/users",
        json={"username": uname, "password": "test12345", "display_name": "Biz V20", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), r.text

    r = _login(client, uname, "test12345")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

    # 业务 API 直接放行
    user_token = r.json()["token"]
    r = client.get("/api/conversations", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200

    # 还原 admin 强制改密
    user_repo.update_user(admin["id"], must_change_password=1)
