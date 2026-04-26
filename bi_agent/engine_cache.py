import time
from collections import defaultdict
from pathlib import Path

import config as cfg
import persistence
import db_connector

_UPLOADS_DB = Path(__file__).parent / "data" / "uploads.db"
_upload_engine = db_connector.create_sqlite_engine(str(_UPLOADS_DB))

# 缓存粒度从 user 改为 (user_id, host:port:user) — 同一 user 的多组连接互不覆盖
_engine_cache: dict = {}
_TTL_SEC = 3600


def _group_key(src: dict) -> str:
    """按 (host, port, user) 标识一个连接组。"""
    return f"{src['db_host']}:{src['db_port']}:{src['db_user']}"


def _split_databases(db_database: str) -> list:
    return [d.strip() for d in (db_database or "").split(',') if d.strip()]


def get_user_engine(user: dict):
    """
    返回 (engine, schema)。

    v0.2.1 修复：原代码 `primary = sources[0]` + 合并所有 source 的 db_database
    会用第一个 source 的账号去访问其他 source 的库 → "无权限"。
    现按 (host, port, user) 对 sources 分组：
      - 同组：合并 db_database 建一个 engine（用户实际场景：同项目共享连接，多库聚合）
      - 多组：仅使用第一组并打 warning（跨连接 schema 合并放下一轮）
    """
    uid = user["id"]
    now = time.time()

    source_ids = persistence.get_user_source_ids(uid)
    if not source_ids and user.get("default_source_id"):
        source_ids = [user["default_source_id"]]

    if source_ids:
        sources = [s for sid in source_ids if (s := persistence.get_datasource(sid)) and s["is_active"]]
        if sources:
            # 按 (host, port, user) 分组
            groups: dict = defaultdict(list)
            for src in sources:
                groups[_group_key(src)].append(src)

            if len(groups) > 1:
                print(
                    f"[engine_cache] WARN user_id={uid} has {len(groups)} datasource groups "
                    f"({list(groups.keys())}); v0.2.1 only supports a single (host,port,user) group, "
                    f"using the first one. 跨连接合并见下一轮 todo。"
                )

            primary_key, primary_sources = next(iter(groups.items()))
            cache_key = (uid, primary_key)
            cached = _engine_cache.get(cache_key)
            if cached and (now - cached["ts"]) < _TTL_SEC:
                return cached["engine"], cached["schema"]

            primary = primary_sources[0]
            try:
                # 同组内合并 db_database
                seen, databases = set(), []
                for src in primary_sources:
                    for db in _split_databases(src["db_database"]):
                        if db not in seen:
                            seen.add(db)
                            databases.append(db)

                engine = db_connector.create_engine(
                    primary["db_host"], primary["db_port"], primary["db_user"],
                    primary["db_password"], primary["db_database"],
                )
                ok, _ = db_connector.test_connection(engine)
                if ok:
                    schema = db_connector.get_schema(engine, databases=databases, max_tables=cfg.SCHEMA_FILTER_MAX_TABLES)
                    _engine_cache[cache_key] = {"engine": engine, "schema": schema, "databases": databases, "ts": now}
                    return engine, schema
            except Exception as e:
                print(f"[engine_cache] WARN user_id={uid} failed to build engine for group {primary_key}: {e}")

    # Fallback: legacy doris_* fields on users 表
    if user.get("doris_user") and user.get("doris_password"):
        legacy_key = f"{user.get('doris_host') or cfg.DEFAULT_DB_HOST}:{user.get('doris_port') or cfg.DEFAULT_DB_PORT}:{user['doris_user']}"
        cache_key = (uid, legacy_key)
        cached = _engine_cache.get(cache_key)
        if cached and (now - cached["ts"]) < _TTL_SEC:
            return cached["engine"], cached["schema"]
        try:
            db_database = user["doris_database"] or cfg.DEFAULT_DB_DATABASE
            engine = db_connector.create_engine(
                user["doris_host"] or cfg.DEFAULT_DB_HOST,
                int(user["doris_port"] or cfg.DEFAULT_DB_PORT),
                user["doris_user"],
                user["doris_password"],
                db_database,
            )
            ok, _ = db_connector.test_connection(engine)
            if ok:
                databases = _split_databases(db_database)
                schema = db_connector.get_schema(engine, databases=databases, max_tables=cfg.SCHEMA_FILTER_MAX_TABLES)
                _engine_cache[cache_key] = {"engine": engine, "schema": schema, "databases": databases, "ts": now}
                return engine, schema
        except Exception:
            pass

    return None, ""


def invalidate_engine_cache(user_id: int):
    """清掉某 user 名下的所有连接组缓存。"""
    keys_to_drop = [k for k in _engine_cache if isinstance(k, tuple) and k[0] == user_id]
    for k in keys_to_drop:
        _engine_cache.pop(k, None)


def get_user_databases(user_id: int):
    """返回当前 user 主连接组的 databases 列表（供 schema 接口等使用）。"""
    for key, val in _engine_cache.items():
        if isinstance(key, tuple) and key[0] == user_id:
            return val.get("databases")
    return None
