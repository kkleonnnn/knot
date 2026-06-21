"""knot/api/admin/datasources.py — 数据源管理 + DataSources Hero stats 路由（admin.py 拆分 v0.6.5.11）。"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Request

from knot.adapters.db import doris as db_connector
from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.api.schemas import DataSourceRequest, UpdateDataSourceRequest
from knot.repositories import data_source_repo

# v0.6.1.3 — DataSources Hero stats 5min 模块级缓存（避免每次切 tab 都打远程 DB）
_DS_STATS_CACHE: dict = {"data": None, "ts": 0.0}
_DS_STATS_TTL_SEC = 300

router = APIRouter()


@router.get("/api/admin/datasources")
async def admin_list_datasources(admin=Depends(require_admin)):
    sources = data_source_repo.list_datasources()

    def _test_source(s):
        # v0.6.1.4 OVERRIDE #4: db_type='http' — base_url HEAD 5s probe；其他走 SQL ping
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

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        statuses = await asyncio.gather(
            *[loop.run_in_executor(pool, _test_source, s) for s in sources]
        )

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

    return [
        {
            "id": s["id"], "name": s["name"],
            "description": s.get("description", ""),
            "db_type": s.get("db_type", "doris"),
            "db_host": s["db_host"], "db_port": s["db_port"],
            "db_database": s["db_database"],
            "base_url": _http_base_url(s),  # v0.6.1.4: HTTP 展示用
            "is_active": s["is_active"], "created_at": s["created_at"],
            "status": status,
        }
        for s, status in zip(sources, statuses)
    ]


@router.post("/api/admin/datasources")
async def admin_create_datasource(req: DataSourceRequest, request: Request, admin=Depends(require_admin)):
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
    if kwargs:
        data_source_repo.update_datasource(source_id, **kwargs)
    audit(request, admin, action="datasource.update", resource_type="datasource",
          resource_id=source_id, detail={"fields": sorted(kwargs.keys())})
    return {"ok": True}


@router.delete("/api/admin/datasources/{source_id}")
async def admin_delete_datasource(source_id: int, request: Request, admin=Depends(require_admin)):
    data_source_repo.delete_datasource(source_id)
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
    if _DS_STATS_CACHE["data"] is not None and now - _DS_STATS_CACHE["ts"] < _DS_STATS_TTL_SEC:
        return _DS_STATS_CACHE["data"]

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
    except Exception:
        pass

    result = {
        "total_schemas": schemas,
        "total_tables": tables_total,
        "last_heartbeat": last_heartbeat,
    }
    _DS_STATS_CACHE["data"] = result
    _DS_STATS_CACHE["ts"] = now
    return result
