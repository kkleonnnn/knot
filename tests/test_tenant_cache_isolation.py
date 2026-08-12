"""v0.9.1 — 进程内租户状态 per-tenant 化：跨租户交叉未命中测。

纯 in-process，直调 `set_active_tenant`（**永不** resolve_single_tenant → R-T-GATE 不动、无需第二 platform.db 行）。
覆盖 5 个 IN 缓存 + 两颗守护者重点陷阱：**MF1 token 跨租户吊销隔离** + **G2 invalidate_all 非对称**。
autouse `_master_key_for_tests` 已设 tenant#1 ctx；tenant#2 场景显式 set/reset。
"""
import time

import pytest

from knot.core.tenant_context import (
    reset_active_tenant,
    set_active_tenant,
    tenant_cache_key,
)

_T2 = {"id": 2, "slug": "t2", "name": "T2", "status": "active", "db_dir": "tenants/2"}


# ─────────────────────── MF1 token cache（安全 critical）───────────────────────

def test_token_version_cache_cross_tenant_isolation():
    """MF1：同 user_id=1 在两租户各自版本，互不串（否则 B 已吊销 token 命中 A 缓存 ver → 吊销绕过 / 错 401）。"""
    import knot.services.totp_service as totp
    totp._TOKEN_VERSION_CACHE.clear()
    totp._TOKEN_VERSION_CACHE[tenant_cache_key(1)] = 5     # tenant#1 user1 → ver 5
    assert totp.get_token_version_cached(1) == 5           # tenant#1 命中自己的
    tok = set_active_tenant(_T2)
    try:
        totp._TOKEN_VERSION_CACHE[tenant_cache_key(1)] = 2  # tenant#2 user1 → ver 2（键 (2,1)，不覆盖 (1,1)）
        assert totp.get_token_version_cached(1) == 2        # tenant#2 见 2，**非** tenant#1 的 5
    finally:
        reset_active_tenant(tok)
    assert totp.get_token_version_cached(1) == 5           # 回 tenant#1 仍 5（未被污染）


def test_token_invalidate_single_user_tenant_scoped():
    """single-user pop 仅清当前租户 (tid,uid)，不碰别租户同 user_id。"""
    import knot.services.totp_service as totp
    totp._TOKEN_VERSION_CACHE.clear()
    totp._TOKEN_VERSION_CACHE[(1, 1)] = 5
    totp._TOKEN_VERSION_CACHE[(2, 1)] = 2
    totp.invalidate_token_version_cache(1)          # tenant#1 ctx（autouse）
    assert (1, 1) not in totp._TOKEN_VERSION_CACHE
    assert (2, 1) in totp._TOKEN_VERSION_CACHE      # tenant#2 的未动


def test_token_invalidate_all_stays_global():
    """⭐ G2 非对称：token invalidate_all 保持真全局 .clear()（rollout 全员事件）→ 两租户全清。"""
    import knot.services.totp_service as totp
    totp._TOKEN_VERSION_CACHE.clear()
    totp._TOKEN_VERSION_CACHE[(1, 1)] = 5
    totp._TOKEN_VERSION_CACHE[(2, 1)] = 2
    totp.invalidate_all_token_version_cache()
    assert len(totp._TOKEN_VERSION_CACHE) == 0      # 两租户都清（收成 tenant-scoped 会留 stale = 安全洞）


# ─────────────────────── engine cache（凭据泄漏，主雷）───────────────────────

def test_engine_for_source_cross_tenant_no_reuse(monkeypatch):
    """跨租户同 source_id 绝不复用引擎（否则 B 重跑打 A 库/凭据）—— (tid,"source",sid) 键隔离。"""
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    src = {"is_active": True, "db_host": "h", "db_port": 9030,
           "db_user": "u", "db_password": "p", "db_database": "x"}
    monkeypatch.setattr(ec.data_source_repo, "get_datasource", lambda sid: src)
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(ec.db_connector, "test_connection", lambda e: (True, ""))

    e1 = ec.get_engine_for_source(5)                # tenant#1
    tok = set_active_tenant(_T2)
    try:
        e2 = ec.get_engine_for_source(5)            # tenant#2 同 source_id
    finally:
        reset_active_tenant(tok)
    assert e1 is not None and e2 is not None
    assert e1 is not e2, "跨租户同 source_id 复用了引擎（凭据泄漏）"
    assert ec.get_engine_for_source(5) is e1        # tenant#1 再取命中自己的


def _stub_engine_build(monkeypatch, ec, get_datasource, source_ids):
    """mock get_user_engine 的 DB 依赖，create_engine 每次返新 object()（供跨租户不复用断言）。"""
    monkeypatch.setattr(ec.data_source_repo, "get_user_source_ids", lambda uid: source_ids)
    monkeypatch.setattr(ec.data_source_repo, "get_datasource", get_datasource)
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(ec.db_connector, "test_connection", lambda e: (True, ""))
    monkeypatch.setattr(ec.db_connector, "check_readonly_grants", lambda e: ("unknown", ""))
    monkeypatch.setattr(ec.db_connector, "get_schema", lambda e, **k: "schema")


def test_get_user_engine_single_group_cross_tenant_no_reuse(monkeypatch):
    """【对抗 #4 补 · producer 侧主凭据泄漏面】get_user_engine 单组分支跨租户不复用引擎。

    这是 PATCH 的主泄漏面（此前仅 source 分支有 e2e 覆盖）；revert engine_cache.py:184 的 tid 前缀 → 本测转红。
    """
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    src = {"id": 3, "is_active": 1, "db_host": "h", "db_port": 9030,
           "db_user": "u", "db_password": "p", "db_database": "x"}
    _stub_engine_build(monkeypatch, ec, lambda sid: src, [3])
    user = {"id": 7}
    e1, _ = ec.get_user_engine(user)              # tenant#1
    tok = set_active_tenant(_T2)
    try:
        e2, _ = ec.get_user_engine(user)          # tenant#2 同 uid + 同源
    finally:
        reset_active_tenant(tok)
    assert e1 is not None and e2 is not None
    assert e1 is not e2, "跨租户同 uid+源复用了引擎（凭据泄漏）"
    # ⚠️ v0.9.23 R10'-A：键**尾部**追加了连接指纹 ⇒ 此处**不能**再断精确三元组
    #    （原文 `assert (1,7,gk) in _engine_cache` 已实测在指纹落地后必红）。
    # ⭐ **改的是判据形状，不是判据本身** —— 本测要证的仍是「两个租户各有自己的条目」，
    #    而它**顺带成了「指纹只能加在尾部」这条红线的守护**：
    #    断言前缀恰为 `(tid, 7, gk)` 且**只多出一段** ⇒ 若哪天有人把指纹插到中间，本行会红。
    gk = ec._group_key(src)
    keys = [k for k in ec._engine_cache if isinstance(k, tuple)]
    for tid in (1, 2):
        matched = [k for k in keys if k[:3] == (tid, 7, gk)]
        assert len(matched) == 1, f"tenant#{tid} 的条目应恰 1 条，实际 {matched}"
        assert len(matched[0]) == 4, (
            f"缓存键形状应为 (tid, uid, group_key, fp) 共 4 段，实际 {matched[0]!r} —— "
            "⚠️ 指纹必须在**尾部**：`invalidate_user_engine_cache` 与 `get_user_databases` "
            "都按位置解析 k[0]/k[1]，插在中间会静默废掉这两个消费者。"
        )


def test_get_user_engine_multigroup_cross_tenant_no_reuse(monkeypatch):
    """【对抗 #4 补】多组分支（engine_cache.py:186 "multi:" 键）跨租户不复用。"""
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    srcs = {
        3: {"id": 3, "is_active": 1, "db_host": "h1", "db_port": 9030, "db_user": "u", "db_password": "p", "db_database": "a"},
        4: {"id": 4, "is_active": 1, "db_host": "h2", "db_port": 9030, "db_user": "u", "db_password": "p", "db_database": "b"},
    }
    _stub_engine_build(monkeypatch, ec, lambda sid: srcs[sid], [3, 4])
    user = {"id": 9}
    e1, _ = ec.get_user_engine(user)
    tok = set_active_tenant(_T2)
    try:
        e2, _ = ec.get_user_engine(user)
    finally:
        reset_active_tenant(tok)
    assert e1 is not e2, "multi-group 分支跨租户复用引擎"


def test_get_user_engine_legacy_branch_cross_tenant_no_reuse(monkeypatch):
    """【对抗 #4 补】legacy doris_* 分支（engine_cache.py:271 键）跨租户不复用。"""
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    monkeypatch.setattr(ec.data_source_repo, "get_user_source_ids", lambda uid: [])
    monkeypatch.setattr(ec.db_connector, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(ec.db_connector, "test_connection", lambda e: (True, ""))
    monkeypatch.setattr(ec.db_connector, "get_schema", lambda e, **k: "schema")
    user = {"id": 8, "doris_host": "h", "doris_port": 9030, "doris_user": "du",
            "doris_password": "dp", "doris_database": "ddb"}
    e1, _ = ec.get_user_engine(user)
    tok = set_active_tenant(_T2)
    try:
        e2, _ = ec.get_user_engine(user)
    finally:
        reset_active_tenant(tok)
    assert e1 is not None and e2 is not None
    assert e1 is not e2, "legacy 分支跨租户复用引擎"


def test_engine_invalidators_scope_and_asymmetry():
    """MF3 三拆 + G2：user 版仅当前租户 (tid,uid)；tenant 版清当前租户全 user+source；**绝不 nuke 别租户**。"""
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    ec._engine_cache[(1, 7, "g")] = {"ts": 9e18}       # t1 user7
    ec._engine_cache[(1, "source", 3)] = {"ts": 9e18}  # t1 source
    ec._engine_cache[(2, 7, "g")] = {"ts": 9e18}       # t2 user7
    ec.invalidate_user_engine_cache(7)                 # tenant#1 ctx
    assert (1, 7, "g") not in ec._engine_cache
    assert (1, "source", 3) in ec._engine_cache        # user 版不碰 source（MF3 方向纠正）
    assert (2, 7, "g") in ec._engine_cache             # 别租户不动
    ec.invalidate_tenant_engine_cache()                # tenant#1 删源用
    assert (1, "source", 3) not in ec._engine_cache    # 当前租户 source 也清
    assert (2, 7, "g") in ec._engine_cache             # ⭐ 删 A 不 nuke B（与 token 全局清相反）


def test_get_user_databases_tenant_scoped():
    """get_user_databases 只返当前租户该 user 的库列表。"""
    import knot.services.engine_cache as ec
    ec._engine_cache.clear()
    ec._engine_cache[(1, 7, "g")] = {"databases": ["t1db"], "ts": 9e18}
    ec._engine_cache[(2, 7, "g")] = {"databases": ["t2db"], "ts": 9e18}
    assert ec.get_user_databases(7) == ["t1db"]        # tenant#1
    tok = set_active_tenant(_T2)
    try:
        assert ec.get_user_databases(7) == ["t2db"]    # tenant#2 见自己的
    finally:
        reset_active_tenant(tok)


# ─────────────────────── rate-limit authed 桶 ───────────────────────

def test_rate_limit_authed_bucket_cross_tenant():
    """MF8：authed 桶跨租户独立配额（tenant#1 打满不影响 tenant#2 同 user_id）。"""
    from fastapi import HTTPException

    from knot.api import _rate_limit as rl
    rl._reset_for_tests()
    limit = rl._DEFAULT_LIMITS["totp_verify"][0]
    for _ in range(limit):
        rl.enforce_totp_verify_rate_limit(1)            # tenant#1 user1 打到上限
    with pytest.raises(HTTPException):
        rl.enforce_totp_verify_rate_limit(1)            # tenant#1 超限 429
    tok = set_active_tenant(_T2)
    try:
        rl.enforce_totp_verify_rate_limit(1)            # tenant#2 同 user_id → 独立桶，不超限
    finally:
        reset_active_tenant(tok)


# ─────────────────────── datasources 两缓存 ───────────────────────

def test_ds_status_cache_cross_tenant_miss():
    """#4：_DS_STATUS_CACHE (tid,sid) 键 —— tenant#2 同 sid 未命中 tenant#1 的健康状态。"""
    from knot.api.admin import datasources as ds
    ds._DS_STATUS_CACHE.clear()
    ds._DS_STATUS_CACHE[tenant_cache_key(1)] = ("online", time.time())
    assert ds._cached_status(1) == "online"             # tenant#1
    tok = set_active_tenant(_T2)
    try:
        assert ds._cached_status(1) == "checking"       # tenant#2 sid=1 未命中（非 A 的 online）
    finally:
        reset_active_tenant(tok)


def test_ds_stats_cache_endpoint_cross_tenant_isolation(monkeypatch, tmp_db_path):
    """#5 硬化（守护者 Stage 4）：**驱动生产端点** admin_datasources_stats 于两租户 ctx 证隔离 + R-AS-2 身份。

    ⚠️ **`tmp_db_path` 是 v0.9.15 补的，不是装饰**：本文件其余 11 条只碰内存缓存，
    唯独本条**驱动真端点** ⇒ 会走到 `get_conn()`。缺了它就用**真实** `SQLITE_DB_PATH` 解析
    ⇒ 在 `knot/data/tenants/2/` 建出一个真实的库文件。
    ⭐ **它已经这样静默跑了很久** —— 实测数据目录里那个「来历不明」的 `tenants/2`
    （2026-07-29 的空库、0 张表、平台库里无对应行）**就是本测建的**。
    在 `conftest::_no_test_may_touch_real_data_dir` 装上之前，**没有任何东西会响**。

    原测自填自读 `.get(tid)` = tautology（不走端点，端点 revert 成全局键也不红）。改用「list_datasources 调用次数」
    作 cache-miss/重算的探针：tenant#1 首调 miss(算一次) + 再调 hit(不算)；tenant#2 若隔离→miss 重算(第 2 次)，
    若端点 revert 成全局键→命中 tenant#1 缓存不重算(仍 1 次)→本测转红。故对 datasources.py:230/292 的 tid 键 revert-sensitive。
    """
    import asyncio

    from knot.api import admin
    from knot.api.admin import datasources as ds
    assert admin._DS_STATS_CACHE is ds._DS_STATS_CACHE  # R-AS-2 同对象（re-export）
    ds._DS_STATS_CACHE.clear()
    calls = []
    monkeypatch.setattr(ds.data_source_repo, "list_datasources", lambda: calls.append(1) or [])
    fake_admin = {"id": 1, "role": "admin"}

    asyncio.run(ds.admin_datasources_stats(admin=fake_admin))   # tenant#1 miss → 重算（calls=1）
    asyncio.run(ds.admin_datasources_stats(admin=fake_admin))   # tenant#1 hit → 不重算
    assert len(calls) == 1, "tenant#1 第 2 次应命中缓存（不重算）"

    tok = set_active_tenant(_T2)
    try:
        asyncio.run(ds.admin_datasources_stats(admin=fake_admin))   # tenant#2 miss（隔离）→ 重算
    finally:
        reset_active_tenant(tok)
    assert len(calls) == 2, "tenant#2 缓存未命中重算 = 隔离；全局缓存则命中不重算 = 泄漏（转红）"
