"""集成测试 fixtures：每条测试一个独立 tmp SQLite + TestClient。

不依赖 LLM API key / Doris；只覆盖 routers→services→repos 的纯 Python 链路。
"""
import os
import tempfile

import pytest

from tests.conftest import NoAmbientTenantTestClient


@pytest.fixture()
def client(monkeypatch):
    # v0.9.0 C2 双层布局：mkdtemp + anchor=dir/knot.db + platform.db（middleware resolve_single_tenant 需）。
    # tenant#1 db_dir='.' → anchor 本身。base + tenant_repo 各拷 SQLITE_DB_PATH → 分别 monkeypatch。
    d = tempfile.mkdtemp(prefix="knot_int_")
    anchor = os.path.join(d, "knot.db")

    from knot.repositories import base as base_mod
    from knot.repositories import tenant_repo as _tr
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", anchor)
    monkeypatch.setattr(_tr, "SQLITE_DB_PATH", anchor)
    _tr.init_platform_db()                 # middleware / 启动序 resolve_single_tenant 需 platform.db
    _tr.seed_default_tenant(db_dir=".")    # tenant#1 db_dir='.' → anchor 本身（tenant ctx 由 autouse + middleware 提供）
    base_mod.init_db()

    # v0.6.0.20：默认 admin seed 必须改密；测试场景统一 reset 让业务 API 可调
    # 专门测强制改密的用例（tests/api/test_force_change_password.py）会自己再设回 1
    from knot.repositories import user_repo
    admin = user_repo.get_user_by_username("admin")
    if admin and admin.get("must_change_password"):
        user_repo.update_user(admin["id"], must_change_password=0)

    # 重新 import main 触发 app factory（模块级启动序已跑过；TestClient 共用 app）
    from knot.main import app
    with NoAmbientTenantTestClient(app) as c:
        yield c

    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def admin_token(client):
    """登录 seed admin 账号，返回 Bearer token。

    v0.6.0.20：client fixture 已 reset must_change_password=0；本 fixture 仅做登录。
    专门测强制改密的用例在 tests/api/test_force_change_password.py。
    """
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
