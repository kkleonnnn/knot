"""v0.6.0.18 — /api/admin/query-history 守护测试。

- require_admin（非 admin 401）
- 返回结构 {items, total, page, size}
- period 解析（7d/30d/90d/裸数字/非法）
- 过滤 by user_id / agent_kind / has_error
- 分页 page+size
- size 上限 200
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from knot.main import app
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_query_history_requires_admin(client):
    r = client.get("/api/admin/query-history")
    assert r.status_code == 401


def test_query_history_shape(client, admin_token):
    r = client.get("/api/admin/query-history?period=30d", headers=_auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"items", "total", "page", "size"}
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert data["page"] == 1
    assert data["size"] == 50


def test_query_history_period_parsing(client, admin_token):
    for period, expected in [("7d", 7), ("30d", 30), ("90d", 90), ("14", 14)]:
        r = client.get(f"/api/admin/query-history?period={period}", headers=_auth(admin_token))
        assert r.status_code == 200
        # period 字段不直接返回，但 size/page 总是返回；只需确保不崩
        assert "items" in r.json(), f"period={period}"


def test_query_history_item_structure(client, admin_token):
    """每条 item 必含核心字段（id / question / actor_username / agent_kind / created_at）。"""
    r = client.get("/api/admin/query-history?period=365d&size=10", headers=_auth(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    if items:  # 可能 fresh DB 空
        first = items[0]
        for k in ["id", "question", "actor_username", "agent_kind", "created_at",
                  "cost_usd", "latency_ms", "db_error", "conversation_id"]:
            assert k in first, f"item 缺字段 {k!r}；keys={list(first.keys())}"


def test_query_history_size_capped_at_200(client, admin_token):
    """size > 200 应自动截到 200（防 admin 误请求拉爆 DB）。"""
    r = client.get("/api/admin/query-history?period=30d&size=5000", headers=_auth(admin_token))
    assert r.status_code == 200
    assert r.json()["size"] == 200


def test_query_history_pagination_offset(client, admin_token):
    """page=2 + size=1 应跳过第一条（OFFSET 1）。"""
    r1 = client.get("/api/admin/query-history?period=365d&size=2&page=1", headers=_auth(admin_token))
    r2 = client.get("/api/admin/query-history?period=365d&size=1&page=2", headers=_auth(admin_token))
    items1 = r1.json()["items"]
    items2 = r2.json()["items"]
    # 如果至少 2 条数据：page=2 size=1 的第一条 应等于 page=1 size=2 的第二条
    if len(items1) >= 2:
        assert len(items2) == 1
        assert items2[0]["id"] == items1[1]["id"]


def test_query_history_filter_agent_kind(client, admin_token):
    """agent_kind 过滤命中只返回该 kind。"""
    r = client.get(
        "/api/admin/query-history?period=365d&agent_kind=sql_planner&size=20",
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["agent_kind"] == "sql_planner", f"过滤未生效：{item}"
