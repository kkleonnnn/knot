"""knot/api/admin/datasources.py — 数据源管理 + DataSources Hero stats 路由（admin.py 拆分 v0.6.5.11）。"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Request

from knot.adapters.db import doris as db_connector
from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.api.schemas import DataSourceRequest, UpdateDataSourceRequest
from knot.core.tenant_context import current_tenant, tenant_cache_key
from knot.core.tenant_context import reraise_if_tenant_error as _reraise_if_tenant_error
from knot.repositories import data_source_repo


def _assert_http_base_url_allowed(db_type, http_config) -> None:
    """v0.8.20 F4（SSRF）：存 http 数据源前校验 base_url 过 egress allowlist —— 与 executor.py:97
    单一守卫对齐，防 admin UI 存任意内网 endpoint（url_allowlist docstring 明示的威胁模型）。
    非 http / 无 base_url / 非法 JSON → 放行（下游处理）；base_url 不在 allowlist → 400。"""
    if db_type != "http" or not http_config:
        return
    import json as _json

    from knot.adapters.http.url_allowlist import is_url_allowed
    try:
        base_url = (_json.loads(http_config).get("base_url") or "").rstrip("/")
    except (ValueError, TypeError):
        return
    if base_url and not is_url_allowed(base_url):
        raise HTTPException(status_code=400, detail="base_url host 不在 KNOT_HTTP_ALLOWED_HOSTS 内（egress 白名单）")

# v0.6.1.3 — DataSources Hero stats 5min 模块级缓存（避免每次切 tab 都打远程 DB）
# v0.9.1 MF5：形状 {tid: {"data","ts"}}（对象内按租户分槽 — 防跨租户聚合 stats 泄漏）。
# **保持外层对象身份**（R-AS-2：admin/__init__.py re-export 同对象 + 测 in-place 突变 / .clear()）—— 键在对象内，绝不 rebind。
_DS_STATS_CACHE: dict = {}
_DS_STATS_TTL_SEC = 300

# v0.8.21 体验：数据源健康探测结果缓存（{source_id: (status, ts)}）—— 列表端点不再内联阻塞探测
# （不可达源 TCP 可卡分钟级），status 取缓存 / "checking"；真探测走独立 /status 端点（前端异步调）。
_DS_STATUS_CACHE: dict = {}
_DS_STATUS_TTL_SEC = 300

router = APIRouter()


def _test_source(s):
    # v0.6.1.4 OVERRIDE #4: db_type='http' — base_url HEAD 5s probe；其他走 SQL ping。
    # v0.8.21：由列表内联移到模块级 + 独立 /status 端点调（前端异步，不阻塞列表渲染）。
    if s.get("db_type") == "http":
        try:
            import json as _json

            import requests as _rq
            cfg_str = s.get("http_config") or ""
            if not cfg_str:
                return "error"
            obj = _json.loads(cfg_str)
            base_url = (obj.get("base_url") or "").rstrip("/")
            if not base_url:
                return "error"
            # v0.8.20 F4（SSRF）：探测前过 egress allowlist（原 HEAD 绕过 KNOT_HTTP_ALLOWED_HOSTS
            # → 存进去的内网 base_url 每次列表加载即被 HEAD 探测）；不在白名单不探测。
            from knot.adapters.http.url_allowlist import is_url_allowed
            if not is_url_allowed(base_url):
                return "error"
            # HEAD 比 GET 快（不下载 body）；任何 HTTP 响应（含 4xx/405/5xx）= server alive
            # 仅 Timeout / ConnectionError = 真的不可达
            _rq.head(base_url, timeout=5, allow_redirects=False)
            return "online"
        except _rq.Timeout:
            return "error"
        except _rq.ConnectionError:
            return "error"
        except Exception:
            # JSON 解析失败 / 其他异常 → 保守 error
            return "error"
    try:
        engine = db_connector.create_engine(
            s["db_host"], s["db_port"], s["db_user"], s["db_password"], s["db_database"]
        )
        ok, _ = db_connector.test_connection(engine)
        return "online" if ok else "error"
    except Exception:
        return "error"


# v0.6.1.4 OVERRIDE #4: HTTP type 解 http_config 抽 base_url 供前端展示（不漏 auth_value）
def _http_base_url(s):
    if s.get("db_type") != "http":
        return ""
    try:
        import json as _json
        obj = _json.loads(s.get("http_config") or "")
        return obj.get("base_url") or ""
    except Exception:
        return ""


def _cached_status(sid) -> str:
    """v0.8.21：取缓存健康状态；无 / 过期 → "checking"（前端异步 /status 更新）。

    v0.9.1：键 (tid, sid)（tenant_cache_key）—— sid 是 per-tenant AUTOINCREMENT，跨租户同 sid 会串健康状态。
    """
    v = _DS_STATUS_CACHE.get(tenant_cache_key(sid))
    return v[0] if (v and (time.time() - v[1]) < _DS_STATUS_TTL_SEC) else "checking"


@router.get("/api/admin/datasources")
async def admin_list_datasources(admin=Depends(require_admin)):
    # v0.8.21 体验：**列表不阻塞探测** —— 原每次加载对每个源实时建连（不可达源 TCP 可卡分钟级 →
    # 数据源/用户页各卡 >1min）。改：即时返元数据 + status 取缓存（无/过期→"checking"）；真探测
    # 由前端异步调 GET /status 更新。→ 页面秒开，源挂了也不拖。
    sources = data_source_repo.list_datasources()
    return [
        {
            "id": s["id"], "name": s["name"],
            "description": s.get("description", ""),
            "db_type": s.get("db_type", "doris"),
            "db_host": s["db_host"], "db_port": s["db_port"],
            "db_database": s["db_database"],
            "base_url": _http_base_url(s),  # v0.6.1.4: HTTP 展示用
            "is_active": s["is_active"], "created_at": s["created_at"],
            "status": _cached_status(s["id"]),
        }
        for s in sources
    ]


@router.get("/api/admin/datasources/status")
async def admin_datasources_status(admin=Depends(require_admin)):
    # v0.8.21：实时探测所有源（并发；可能慢，前端异步调不阻塞列表）+ 写缓存 → 返 {id: status}。
    sources = data_source_repo.list_datasources()
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        statuses = await asyncio.gather(
            *[loop.run_in_executor(pool, _test_source, s) for s in sources]
        )
    now = time.time()
    result = {}
    for s, st in zip(sources, statuses):
        _DS_STATUS_CACHE[tenant_cache_key(s["id"])] = (st, now)
        result[s["id"]] = st
    return result


@router.post("/api/admin/datasources")
async def admin_create_datasource(req: DataSourceRequest, request: Request, admin=Depends(require_admin)):
    _assert_http_base_url_allowed(req.db_type, req.http_config)  # v0.8.20 F4：存前校验 egress allowlist
    sid = data_source_repo.create_datasource(
        user_id=admin["id"], name=req.name, description=req.description,
        db_host=req.db_host, db_port=req.db_port, db_user=req.db_user,
        db_password=req.db_password, db_database=req.db_database, db_type=req.db_type,
        http_config=req.http_config,  # v0.6.1.4 OVERRIDE #4
    )
    audit(request, admin, action="datasource.create", resource_type="datasource",
          resource_id=sid, detail={"name": req.name, "db_type": req.db_type,
                                    "db_host": req.db_host, "db_database": req.db_database})
    return {"id": sid, "ok": True}


@router.put("/api/admin/datasources/{source_id}")
async def admin_update_datasource(source_id: int, req: UpdateDataSourceRequest, request: Request, admin=Depends(require_admin)):
    kwargs = {k: v for k, v in req.dict().items() if v is not None}
    # v0.4.5 R-39：db_password 空/mask 占位 → 保留原值
    if "db_password" in kwargs:
        from knot.api._secret import should_update_secret
        existing = data_source_repo.get_datasource(source_id) or {}
        should, _ = should_update_secret(kwargs["db_password"], existing.get("db_password") or "")
        if not should:
            kwargs.pop("db_password")
    # v0.6.1.4: http_config 同模式 — 空 / mask 占位时保留原值（防 admin UI 编辑误清空 token）
    if "http_config" in kwargs:
        import json as _json

        from knot.api._secret import should_update_secret
        existing = data_source_repo.get_datasource(source_id) or {}
        existing_http = existing.get("http_config") or ""
        new_http = kwargs["http_config"]
        # 解 JSON 看 auth_value 是否 mask 占位
        try:
            new_obj = _json.loads(new_http) if new_http else {}
            existing_obj = _json.loads(existing_http) if existing_http else {}
            new_av = new_obj.get("auth_value", "")
            existing_av = existing_obj.get("auth_value", "")
            should, _ = should_update_secret(new_av, existing_av)
            if not should:
                # mask 占位 → 拿原 auth_value 回填
                new_obj["auth_value"] = existing_av
                kwargs["http_config"] = _json.dumps(new_obj, ensure_ascii=False)
        except Exception:
            pass  # JSON 解析失败 → 透传由 repo 决定
    if "http_config" in kwargs:  # v0.8.20 F4：更新写入前校验 base_url egress allowlist（http 源）
        _assert_http_base_url_allowed("http", kwargs["http_config"])
    if kwargs:
        data_source_repo.update_datasource(source_id, **kwargs)
        # v0.9.1 backlog（v0.8 守护者 Stage 4 flagged）：改连接相关字段须清当前租户缓存引擎，
        # 否则旧凭据构建的 engine 存活至 TTL（~1h）继续用旧凭据供查 —— 与 delete 路径对称。
        # kwargs 已过 mask/空占位处理，仅含**实际写入**字段；纯 name/description 元数据编辑不清（免无谓 reconnect）。
        if kwargs.keys() - {"name", "description"}:
            from knot.services.engine_cache import invalidate_tenant_engine_cache
            invalidate_tenant_engine_cache()  # 清当前租户 (tid,uid,group)+(tid,"source",id) 两命名空间
    audit(request, admin, action="datasource.update", resource_type="datasource",
          resource_id=source_id, detail={"fields": sorted(kwargs.keys())})
    return {"ok": True}


@router.delete("/api/admin/datasources/{source_id}")
async def admin_delete_datasource(source_id: int, request: Request, admin=Depends(require_admin)):
    data_source_repo.delete_datasource(source_id)
    from knot.services.engine_cache import invalidate_tenant_engine_cache
    invalidate_tenant_engine_cache()  # v0.8.24 R2 + v0.9.1 MF3：删源撤权，清当前租户 (tid,uid,group)+(tid,"source",id) 两命名空间
    audit(request, admin, action="datasource.delete", resource_type="datasource",
          resource_id=source_id)
    return {"ok": True}


@router.get("/api/admin/datasources-stats")
async def admin_datasources_stats(admin=Depends(require_admin)):
    """v0.6.1.3 — DataSources Hero card 真实 stats（修 v0.5.40 broken impl 500）。

    总 schema: COUNT(DISTINCT db_database) WHERE is_active=1
    总表数: 每个 active source 跑 information_schema.tables COUNT（容错；单 source 失败不影响其它）
    上次心跳: 循环里最近一次成功探测的时间戳

    server 端 5min 模块级缓存（_DS_STATS_CACHE）— admin tab 反复切换不会重打远程 DB。
    """
    import time
    from datetime import datetime

    from sqlalchemy import text as _sa_text

    now = time.time()
    _tid = current_tenant()["id"]
    _slot = _DS_STATS_CACHE.get(_tid)
    if _slot is not None and _slot["data"] is not None and now - _slot["ts"] < _DS_STATS_TTL_SEC:
        return _slot["data"]

    sources = data_source_repo.list_datasources()
    active = [s for s in sources if s.get("is_active") == 1]

    # v0.6.1.4 OVERRIDE #4: db_database 支持逗号分隔多 schema（如 "ohx_ads,ohx_dwd"）；
    # HTTP type 无 SQL schema 概念 → 不计入 schemas，但其虚拟表计入 total_tables。
    def _split_dbs(s):
        return [x.strip() for x in (s.get("db_database") or "").split(",") if x.strip()]

    all_schemas: set = set()
    for s in active:
        if s.get("db_type") == "http":
            continue
        for db in _split_dbs(s):
            all_schemas.add(db)
    schemas = len(all_schemas)

    tables_total = 0
    last_heartbeat = None
    for s in active:
        if s.get("db_type") == "http":
            continue  # HTTP 虚拟表从 catalog 聚合（下面统一加）
        try:
            engine = db_connector.create_engine(
                s["db_host"], s["db_port"], s["db_user"], s["db_password"], s["db_database"]
            )
            dbs = _split_dbs(s) or [s.get("db_database") or ""]
            with engine.connect() as c:
                for db in dbs:
                    # v0.6.1.4 patch — Doris `table_type` 可能不是字面 'BASE TABLE'（实际可能为
                    # 'OLAP TABLE' / NULL / 其他），先尝试 BASE TABLE 过滤；为 0 时退到不过滤兜底
                    # （宁可 +1 view 计入 也好过 0 — v0.6.1.3 "11 vs 12 偏差" 容忍度内）
                    n = c.execute(_sa_text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = :db AND table_type = 'BASE TABLE'"
                    ), {"db": db}).scalar() or 0
                    if n == 0:
                        n = c.execute(_sa_text(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema = :db"
                        ), {"db": db}).scalar() or 0
                    tables_total += int(n)
            last_heartbeat = datetime.now().isoformat(timespec="seconds")
        except Exception:
            # 单 source 探测失败不影响 aggregate；保留已累计 tables_total + 历史 heartbeat
            continue

    # v0.6.1.4 OVERRIDE #4: 累加 HTTP 虚拟表（从 catalog 取 — 0 远程调用）
    try:
        from knot.services.agents import catalog as _catalog
        tables_total += len(_catalog.get_http_tables())
    except Exception as e:
        _reraise_if_tenant_error(e)   # D8'：缺 ctx 不得静默把 HTTP 表数记成 0（观测失真 + 被 tid 缓存固化）

    result = {
        "total_schemas": schemas,
        "total_tables": tables_total,
        "last_heartbeat": last_heartbeat,
    }
    _DS_STATS_CACHE[_tid] = {"data": result, "ts": now}
    return result
