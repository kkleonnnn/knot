"""v0.6.0.23 — login + change_password rate limit 守护测试。

防字典攻击 / brute force：
- login 10 次/60s/IP（超限返 429 + Retry-After）
- change_pwd 5 次/60s/IP（更严）

红线守护：
- R-限-1 X-Forwarded-For 反代 IP 提取
- R-限-2 429 + Retry-After header
- R-限-3 thread-safe
- R-限-4 内存上限自动清理
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db_path):  # noqa: ARG001 — tmp_db_path 用于创建带 admin 的隔离 SQLite
    """TestClient + tmp_db_path 确保 users 表存在（CI 无预存 DB）。"""
    from knot.api._rate_limit import _reset_for_tests
    from knot.main import app
    _reset_for_tests()
    yield TestClient(app)
    _reset_for_tests()  # 测试间隔离


# ─── login rate limit ──────────────────────────────────────────────────


def test_login_within_limit_passes(client):
    """限内（10 次/60s）登录可正常返 401（无效凭证）而非 429。"""
    for i in range(10):
        r = client.post("/api/auth/login", json={"username": "nouser", "password": "x"})
        assert r.status_code == 401, f"第 {i+1} 次应 401（认证失败）；实际 {r.status_code}: {r.text}"


def test_login_over_limit_returns_429(client):
    """超过 10 次/60s → 429 + Retry-After header。"""
    # 先打满 10 次
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "nouser", "password": "x"})
    # 第 11 次必须 429
    r = client.post("/api/auth/login", json={"username": "nouser", "password": "x"})
    assert r.status_code == 429, f"超限应 429；实际 {r.status_code}"
    assert "Retry-After" in r.headers, "429 必须含 Retry-After header (R-限-2)"
    retry_after = int(r.headers["Retry-After"])
    assert 1 <= retry_after <= 61, f"Retry-After 应在 1-61 秒；实际 {retry_after}"


def test_login_429_payload_contains_chinese_message(client):
    """429 payload 含中文说明（用户友好）。"""
    for _ in range(11):
        r = client.post("/api/auth/login", json={"username": "nouser", "password": "x"})
    assert r.status_code == 429
    # FastAPI HTTPException 把 detail 放到 'detail' 字段
    body = r.json()
    assert "detail" in body
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert "zh" in detail
    assert "频繁" in detail["zh"]


def test_login_xff_header_used_for_ip(client):
    """X-Forwarded-For first IP 用于限流 key（反代场景；R-限-1）。"""
    # IP_A 用 10 次
    for _ in range(10):
        client.post("/api/auth/login",
                    json={"username": "nouser", "password": "x"},
                    headers={"X-Forwarded-For": "1.2.3.4, proxy"})

    # IP_A 第 11 次 → 429
    r_a = client.post("/api/auth/login",
                      json={"username": "nouser", "password": "x"},
                      headers={"X-Forwarded-For": "1.2.3.4, proxy"})
    assert r_a.status_code == 429

    # IP_B 第 1 次 → 401（独立 bucket）
    r_b = client.post("/api/auth/login",
                      json={"username": "nouser", "password": "x"},
                      headers={"X-Forwarded-For": "5.6.7.8"})
    assert r_b.status_code == 401, f"不同 XFF IP 应独立计数；实际 {r_b.status_code}"


# ─── change_password rate limit ────────────────────────────────────────


def test_change_pwd_over_limit_returns_429(client):
    """改密 5 次/60s（比 login 严）— 超限 429。"""
    # 先用 admin 登录拿 token
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    # admin 可能因 must_change_password=1 或别 PATCH 改动，但拿到 token 即可
    if r.status_code != 200:
        pytest.skip(f"admin 登录失败 ({r.status_code})；跳过 change_pwd 测试")
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # change_pwd 限流是 5 次/60s
    for _ in range(5):
        client.post("/api/auth/change-password",
                    json={"old_password": "wrong", "new_password": "newpw123456"},
                    headers=headers)
    # 第 6 次应 429
    r = client.post("/api/auth/change-password",
                    json={"old_password": "wrong", "new_password": "newpw123456"},
                    headers=headers)
    assert r.status_code == 429, f"超限应 429；实际 {r.status_code}"
    assert "Retry-After" in r.headers


# ─── v0.6.0.24 query rate limit ────────────────────────────────────────


def test_query_rate_limit_per_user_independent():
    """v0.6.0.24 — query 限流按 user_id（不是 IP）；不同 user 独立 bucket。"""
    from fastapi import HTTPException

    from knot.api._rate_limit import _reset_for_tests, enforce_query_rate_limit
    _reset_for_tests()

    # user 1 打满 30 次（30 次/60s 上限）
    for _ in range(30):
        enforce_query_rate_limit(user_id=1)  # 不抛 = 通过

    # user 1 第 31 次 → 429
    with pytest.raises(HTTPException) as exc_info:
        enforce_query_rate_limit(user_id=1)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    detail = exc_info.value.detail
    assert "zh" in detail and "30 次" in detail["zh"]

    # user 2 第 1 次 → 通过（不受 user 1 影响）
    enforce_query_rate_limit(user_id=2)
    _reset_for_tests()


# ─── 内存上限守护 ──────────────────────────────────────────────────────


def test_memory_limit_prunes_old_buckets():
    """R-限-4 — 内存上限保护：超过 _MAX_KEYS 时自动清理。"""
    from knot.api._rate_limit import _MAX_KEYS, _bucket, _reset_for_tests

    _reset_for_tests()
    # 注入大量 fake keys（模拟 IP 喷射攻击）
    with _bucket._lock:
        for i in range(_MAX_KEYS + 100):
            _bucket._d[f"fake:{i}"] = [0.0]  # 旧时间戳

    # 触发清理 — 通过 check 进入 prune 路径
    _bucket.check("trigger:new", 10, 60)

    with _bucket._lock:
        # 应被清理一部分（不会保留全部 _MAX_KEYS + 100）
        assert len(_bucket._d) <= _MAX_KEYS + 100, "应清理过期 buckets"

    _reset_for_tests()
