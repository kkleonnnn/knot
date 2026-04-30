import re
import time
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text as _sa_text

import config as cfg
import persistence
import db_connector
from logging_setup import logger

# v0.2.4: uploads.db 已合并入 bi_agent.db；上传表与业务表共用一个 SQLite 文件。
# 老 uploads.db 的迁移在 persistence.init_db() 一次性完成（幂等）。
_BIAGENT_DB = Path(__file__).parent / "data" / "bi_agent.db"
_upload_engine = db_connector.create_sqlite_engine(str(_BIAGENT_DB))


# ── 跨连接组多源派发引擎 ──────────────────────────────────────────────────────
#
# 当 user 关联的 datasources 跨多个 (host, port, user) 时，单个 SQLAlchemy engine
# 无法访问其它组的库。MultiSourceEngine 把多个真 engine 包成一个 duck-typed engine：
# - .connect() 返回 _MultiConn（懒开连接、按 SQL 路由）
# - 路由策略：解析 SQL 找首个 `db.tbl` 前缀，匹配 groups 中的 databases
#   找不到时走 default_engine（第一组）
# - 仅支持 SELECT-only 单库查询；跨组 JOIN 不支持
class MultiSourceEngine:
    def __init__(self, groups: list):
        # groups: [{"key": str, "engine": Engine, "databases": [str, ...]}]
        self.groups = groups
        self._db2engine = {}
        for g in groups:
            for db in g["databases"]:
                self._db2engine.setdefault(db.lower(), g["engine"])
        self.default_engine = groups[0]["engine"]
        # 兼容 SQLAlchemy 引擎部分属性（避免外部 isinstance 检查）
        self.url = getattr(self.default_engine, "url", None)

    _DB_TBL_RE = re.compile(
        r"\b(?:from|join|into|update|table)\s+`?([A-Za-z_][\w]*)`?\.`?[A-Za-z_][\w]*`?",
        re.IGNORECASE,
    )

    def _route(self, sql: str):
        if not sql:
            return self.default_engine
        m = self._DB_TBL_RE.search(sql)
        if m:
            db = m.group(1).lower()
            return self._db2engine.get(db, self.default_engine)
        return self.default_engine

    def _referenced_dbs(self, sql: str) -> list:
        """SQL 中所有 db.tbl 引用的 db 名（小写，去重保序）。"""
        if not sql:
            return []
        out, seen = [], set()
        for m in self._DB_TBL_RE.finditer(sql):
            db = m.group(1).lower()
            if db not in seen:
                seen.add(db)
                out.append(db)
        return out

    def cross_group_dbs(self, sql: str):
        """若 SQL 引用的 dbs 跨多个组，返回 (route_group_key, foreign_dbs)；否则 None。
        foreign_dbs 是已在 _db2engine 中但属于其他组的 db 列表。
        未注册的 db（不在任何组）不视作跨组。
        """
        dbs = self._referenced_dbs(sql)
        if len(dbs) <= 1:
            return None
        route_eng = self._db2engine.get(dbs[0])
        if route_eng is None:
            return None
        foreign = []
        for db in dbs[1:]:
            eng = self._db2engine.get(db)
            if eng is not None and eng is not route_eng:
                foreign.append(db)
        if not foreign:
            return None
        # 找 route_eng 对应的 group key
        route_key = next((g["key"] for g in self.groups if g["engine"] is route_eng), "?")
        return route_key, foreign

    def connect(self):
        return _MultiConn(self)


class _MultiConn:
    def __init__(self, multi: MultiSourceEngine):
        self._multi = multi
        self._conn = None
        self._engine = None

    def _open(self, sql: str):
        engine = self._multi._route(sql)
        if self._conn is not None and self._engine is engine:
            return self._conn
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = engine.connect()
        self._engine = engine
        return self._conn

    def execute(self, stmt, params=None):
        # stmt 可能是 sqlalchemy.text() 或字符串
        sql_str = getattr(stmt, "text", None) or (stmt if isinstance(stmt, str) else str(stmt))
        # 跨连接组检测：若 SQL 引用了多个不同组的 db，给出明确错误（不是"无权限"）
        cross = self._multi.cross_group_dbs(sql_str)
        if cross is not None:
            route_key, foreign = cross
            raise RuntimeError(
                f"跨连接组查询不支持：本次路由到组 {route_key}，但 SQL 还引用了其他组的库 "
                f"{foreign}。请改写为单组查询，或先在各组分别查再在应用层合并。"
            )
        conn = self._open(sql_str)
        return conn.execute(stmt if not isinstance(stmt, str) else _sa_text(stmt), params or {})

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

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

            # 缓存 key：单组用 (uid, group_key)；多组用 (uid, "multi:" + 全部 group_key 排序拼接)
            if len(groups) == 1:
                cache_key = (uid, next(iter(groups.keys())))
            else:
                cache_key = (uid, "multi:" + "|".join(sorted(groups.keys())))
            cached = _engine_cache.get(cache_key)
            if cached and (now - cached["ts"]) < _TTL_SEC:
                return cached["engine"], cached["schema"]

            try:
                built = []  # [{key, engine, databases}]
                schema_blocks = []
                per_group_quota = max(cfg.SCHEMA_FILTER_MAX_TABLES // max(len(groups), 1), 4)
                for gkey, gsources in groups.items():
                    primary = gsources[0]
                    seen, databases = set(), []
                    for src in gsources:
                        for db in _split_databases(src["db_database"]):
                            if db not in seen:
                                seen.add(db)
                                databases.append(db)
                    eng = db_connector.create_engine(
                        primary["db_host"], primary["db_port"], primary["db_user"],
                        primary["db_password"], primary["db_database"],
                    )
                    ok, reason = db_connector.test_connection(eng)
                    if not ok:
                        logger.warning(f"engine_cache user_id={uid} group {gkey} test failed: {reason}")
                        continue
                    # 只读权限探测（best-effort，不阻断）
                    try:
                        ro_status, ro_detail = db_connector.check_readonly_grants(eng)
                        if ro_status == "writable":
                            logger.warning(
                                f"engine_cache user_id={uid} group {gkey} 账号疑似有写权限！"
                                f"强烈建议改用只读账号。grants={str(ro_detail)[:200]}"
                            )
                            if getattr(cfg, "STRICT_READONLY_GRANTS", False):
                                logger.warning("STRICT_READONLY_GRANTS=1，拒绝构建该组 engine")
                                continue
                        elif ro_status == "unknown":
                            logger.info(
                                f"engine_cache user_id={uid} group {gkey} 无法探测 grants；依赖 SQL 解析层 guardrail。"
                            )
                    except Exception as _e:
                        logger.debug(f"engine_cache grants probe error (ignored): {_e}")
                    g_schema = db_connector.get_schema(
                        eng, databases=databases,
                        max_tables=(cfg.SCHEMA_FILTER_MAX_TABLES if len(groups) == 1 else per_group_quota),
                    )
                    built.append({"key": gkey, "engine": eng, "databases": databases})
                    if len(groups) > 1:
                        schema_blocks.append(
                            f"## 连接组 {gkey}（包含库：{', '.join(databases)}）\n{g_schema}"
                        )
                    else:
                        schema_blocks.append(g_schema)

                if built:
                    if len(built) == 1:
                        engine = built[0]["engine"]
                        databases = built[0]["databases"]
                        schema = "\n\n".join(schema_blocks)
                    else:
                        engine = MultiSourceEngine(built)
                        databases = [db for g in built for db in g["databases"]]
                        # 多组场景顶部加一段路由约束说明，避免 LLM 跨组 JOIN
                        group_summary = "\n".join(
                            f"  - 组 {g['key']}：{', '.join(g['databases'])}" for g in built
                        )
                        header = (
                            "# 多连接组提示（重要）\n"
                            "本数据源跨多个连接组，每组使用独立账号；不同组的库不能在同一条 SQL 里 JOIN。\n"
                            "组 → 库归属：\n"
                            f"{group_summary}\n"
                            "约束：每条 SQL 只能引用同一组内的库。\n"
                        )
                        schema = header + "\n" + "\n\n".join(schema_blocks)
                    _engine_cache[cache_key] = {
                        "engine": engine, "schema": schema,
                        "databases": databases, "ts": now,
                    }
                    return engine, schema
            except Exception as e:
                logger.warning(f"engine_cache user_id={uid} multi-source build failed: {e}")

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
