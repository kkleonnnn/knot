import time
from pathlib import Path

import config as cfg
import persistence
import db_connector

_UPLOADS_DB = Path(__file__).parent / "data" / "uploads.db"
_upload_engine = db_connector.create_sqlite_engine(str(_UPLOADS_DB))

_engine_cache: dict = {}


def get_user_engine(user: dict):
    uid = user["id"]
    now = time.time()
    cached = _engine_cache.get(uid)
    if cached and (now - cached["ts"]) < 3600:
        return cached["engine"], cached["schema"]

    source_ids = persistence.get_user_source_ids(uid)
    if not source_ids and user.get("default_source_id"):
        source_ids = [user["default_source_id"]]
    if source_ids:
        sources = [s for sid in source_ids if (s := persistence.get_datasource(sid)) and s["is_active"]]
        if sources:
            primary = sources[0]
            try:
                engine = db_connector.create_engine(
                    primary["db_host"], primary["db_port"], primary["db_user"],
                    primary["db_password"], primary["db_database"],
                )
                ok, _ = db_connector.test_connection(engine)
                if ok:
                    seen, databases = set(), []
                    for src in sources:
                        for db in src["db_database"].split(','):
                            db = db.strip()
                            if db and db not in seen:
                                seen.add(db); databases.append(db)
                    schema = db_connector.get_schema(engine, databases=databases, max_tables=cfg.SCHEMA_FILTER_MAX_TABLES)
                    _engine_cache[uid] = {"engine": engine, "schema": schema, "databases": databases, "ts": now}
                    return engine, schema
            except Exception:
                pass

    if user.get("doris_user") and user.get("doris_password"):
        try:
            db_database = user["doris_database"] or cfg.DEFAULT_DB_DATABASE
            engine = db_connector.create_engine(
                user["doris_host"] or cfg.DEFAULT_DB_HOST,
                int(user["doris_port"] or cfg.DEFAULT_DB_PORT),
                user["doris_user"],
                user["doris_password"],
                db_database,
            )
            ok, msg = db_connector.test_connection(engine)
            if ok:
                databases = [d.strip() for d in db_database.split(',') if d.strip()]
                schema = db_connector.get_schema(engine, databases=databases, max_tables=cfg.SCHEMA_FILTER_MAX_TABLES)
                _engine_cache[uid] = {"engine": engine, "schema": schema, "databases": databases, "ts": now}
                return engine, schema
        except Exception:
            pass

    return None, ""


def invalidate_engine_cache(user_id: int):
    _engine_cache.pop(user_id, None)
