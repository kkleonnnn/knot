"""v0.8.24 — data_source 删除撤引擎缓存 + admin PUT 写侧存在性校验（api 层）。

覆盖 MF1（R1 写侧对称校验：default_source_id + source_ids 双入口）+ MF2（R2 删源全清 engine cache 两命名空间）。
"""

_DS = {"name": "d", "description": "", "db_host": "h", "db_port": 9030,
       "db_user": "u", "db_password": "p", "db_database": "x", "db_type": "doris", "http_config": ""}


def _mk_source(client, auth_headers) -> int:
    r = client.post("/api/admin/datasources", json=_DS, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_user(client, auth_headers, username) -> int:
    r = client.post("/api/admin/users",
                    json={"username": username, "password": "pw123456", "role": "analyst"},
                    headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_delete_datasource_invalidates_engine_cache(client, auth_headers):
    """MF2 + v0.9.1 MF3：删源后清**当前租户** engine cache 两命名空间（tid 前缀键）。"""
    from knot.core.tenant_context import tenant_cache_key
    from knot.services import engine_cache
    sid = _mk_source(client, auth_headers)
    engine_cache._engine_cache.clear()
    engine_cache._engine_cache[tenant_cache_key(1, "grp")] = {"engine": object(), "ts": 9e18}       # (tid,uid,group)
    engine_cache._engine_cache[tenant_cache_key("source", sid)] = {"engine": object(), "ts": 9e18}  # (tid,"source",sid)
    assert engine_cache._engine_cache

    r = client.delete(f"/api/admin/datasources/{sid}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert engine_cache._engine_cache == {}, "删源须全清 engine cache 两命名空间"


def test_update_datasource_credential_change_invalidates_engine_cache(client, auth_headers):
    """v0.9.1 backlog（v0.8 守护者 Stage 4 flagged）：改连接字段（此处 db_password）后
    清**当前租户** engine cache 两命名空间（否则旧凭据构建的 engine 存活至 TTL 继续供查）。

    非 tautology：走真 PUT 端点；revert 生产码（删 update 路径 invalidate 调用）→ 缓存存活 → 本测转红。
    """
    from knot.core.tenant_context import tenant_cache_key
    from knot.services import engine_cache
    sid = _mk_source(client, auth_headers)
    engine_cache._engine_cache.clear()
    engine_cache._engine_cache[tenant_cache_key(1, "grp")] = {"engine": object(), "ts": 9e18}       # (tid,uid,group)
    engine_cache._engine_cache[tenant_cache_key("source", sid)] = {"engine": object(), "ts": 9e18}  # (tid,"source",sid)
    assert engine_cache._engine_cache

    r = client.put(f"/api/admin/datasources/{sid}",
                   json={"db_password": "rotated-secret-123"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert engine_cache._engine_cache == {}, "改凭据须清 engine cache 两命名空间（旧凭据 engine 否则存活至 TTL）"


def test_update_datasource_metadata_only_keeps_engine_cache(client, auth_headers):
    """选择性失效：纯 name/description 元数据编辑**不清**缓存（免无谓 reconnect churn）。

    守护「仅 connection-affecting 字段变更才失效」的 denylist 语义；改成「非空 kwargs 一律清」→ 本测转红。
    """
    from knot.core.tenant_context import tenant_cache_key
    from knot.services import engine_cache
    sid = _mk_source(client, auth_headers)
    engine_cache._engine_cache.clear()
    key = tenant_cache_key("source", sid)
    engine_cache._engine_cache[key] = {"engine": object(), "ts": 9e18}

    r = client.put(f"/api/admin/datasources/{sid}",
                   json={"name": "renamed", "description": "just metadata"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert key in engine_cache._engine_cache, "纯元数据编辑不应清 engine cache"


def test_admin_update_user_rejects_nonexistent_default_source(client, auth_headers):
    """MF1/R1：default_source_id 存在性校验。"""
    uid = _mk_user(client, auth_headers, "u_def")
    assert client.put(f"/api/admin/users/{uid}", json={"default_source_id": 9999},
                      headers=auth_headers).status_code == 400
    # None 清空 → 放行
    assert client.put(f"/api/admin/users/{uid}", json={"default_source_id": None},
                      headers=auth_headers).status_code == 200
    # 合法源 → 放行
    sid = _mk_source(client, auth_headers)
    assert client.put(f"/api/admin/users/{uid}", json={"default_source_id": sid},
                      headers=auth_headers).status_code == 200


def test_admin_update_user_rejects_nonexistent_source_ids(client, auth_headers):
    """MF1/R1：source_ids（user_sources 主写入口）存在性校验 —— 修补前可写 [9999] 造悬空。"""
    uid = _mk_user(client, auth_headers, "u_src")
    assert client.put(f"/api/admin/users/{uid}", json={"source_ids": [9999]},
                      headers=auth_headers).status_code == 400
    # 空列表 → 放行
    assert client.put(f"/api/admin/users/{uid}", json={"source_ids": []},
                      headers=auth_headers).status_code == 200
    # 合法源 → 放行
    sid = _mk_source(client, auth_headers)
    assert client.put(f"/api/admin/users/{uid}", json={"source_ids": [sid]},
                      headers=auth_headers).status_code == 200
