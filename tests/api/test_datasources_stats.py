"""tests/api/test_datasources_stats.py — v0.6.1.3 守护 /api/admin/datasources-stats。

修 v0.5.40 broken impl 500（schema_text 列不存在）：
- endpoint 不应 500（即使 0 个 data source）
- 返回 3 个 key: total_schemas / total_tables / last_heartbeat
- 0 source 时 schemas=0 / tables=0 / heartbeat=None（合法的空状态）
- 5min 模块级缓存：连续 2 次调用，第 2 次走 cache（数据 byte-equal）
"""
from __future__ import annotations


def test_endpoint_returns_200_with_empty_db(client, auth_headers):
    """空 DB（无 data_source）时 endpoint 不应 500；返回合法空状态。"""
    r = client.get("/api/admin/datasources-stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) == {"total_schemas", "total_tables", "last_heartbeat"}
    assert data["total_schemas"] == 0
    assert data["total_tables"] == 0
    assert data["last_heartbeat"] is None


def test_endpoint_requires_admin(client):
    """无 token / 非 admin 应被 require_admin 拦截 401/403。"""
    r = client.get("/api/admin/datasources-stats")
    assert r.status_code in (401, 403), r.text


def test_module_level_cache_returns_byte_equal_on_second_call(client, auth_headers):
    """5min 模块级 cache：连续 2 次调用返回字节相等（避免每次重打远程 DB）。"""
    # cache 是模块级；测试间可能受污染 — 此测试容忍：仅断言 2 次结果一致
    from knot.api import admin as admin_mod
    admin_mod._DS_STATS_CACHE["data"] = None  # 强制首次 miss
    admin_mod._DS_STATS_CACHE["ts"] = 0.0

    r1 = client.get("/api/admin/datasources-stats", headers=auth_headers)
    r2 = client.get("/api/admin/datasources-stats", headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json(), "第 2 次必须命中 cache（与首次 byte-equal）"
