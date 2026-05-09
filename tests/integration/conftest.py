"""集成测试 fixtures：每条测试一个独立 tmp SQLite + TestClient。

不依赖 LLM API key / Doris；只覆盖 routers→services→repos 的纯 Python 链路。
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="bi_agent_int_")
    os.close(fd)
    os.unlink(path)

    # patch SQLite 路径
    from knot.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()

    # 重新 import main 触发 app factory（模块级 init_db 已跑过；TestClient 共用 app）
    from knot.main import app
    with TestClient(app) as c:
        yield c

    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture()
def admin_token(client):
    """登录 seed admin 账号，返回 Bearer token。"""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
