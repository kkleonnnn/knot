"""
persistence.py — SQLite 持久化层
"""

import json
import sqlite3
from datetime import datetime

from config import SQLITE_DB_PATH


def get_conn():
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT    UNIQUE NOT NULL,
            password_hash  TEXT    NOT NULL,
            display_name   TEXT,
            role           TEXT    DEFAULT 'analyst',
            doris_host     TEXT,
            doris_port     INTEGER DEFAULT 9030,
            doris_user     TEXT,
            doris_password TEXT,
            doris_database TEXT,
            default_source_id INTEGER,
            is_active      INTEGER DEFAULT 1,
            created_at     TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            title      TEXT    DEFAULT '新对话',
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            question        TEXT,
            sql_text        TEXT,
            explanation     TEXT,
            confidence      TEXT,
            rows_json       TEXT,
            db_error        TEXT,
            cost_usd        REAL    DEFAULT 0,
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            retry_count     INTEGER DEFAULT 0,
            created_at      TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS semantic_layer (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            content    TEXT    DEFAULT '',
            updated_by INTEGER,
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS data_sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            name        TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            db_host     TEXT    NOT NULL,
            db_port     INTEGER DEFAULT 9030,
            db_user     TEXT    NOT NULL,
            db_password TEXT    NOT NULL,
            db_database TEXT    NOT NULL,
            db_type     TEXT    DEFAULT 'doris',
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS model_settings (
            model_key  TEXT PRIMARY KEY,
            enabled    INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS file_uploads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            filename     TEXT    NOT NULL,
            table_name   TEXT    NOT NULL,
            row_count    INTEGER DEFAULT 0,
            columns_json TEXT    DEFAULT '[]',
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS knowledge_docs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            filename    TEXT    NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS doc_chunks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id         INTEGER NOT NULL,
            chunk_text     TEXT    NOT NULL,
            embedding_blob BLOB
        );

        CREATE TABLE IF NOT EXISTS user_sources (
            user_id   INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, source_id)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS few_shots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            question   TEXT    NOT NULL,
            sql        TEXT    NOT NULL,
            type       TEXT    DEFAULT '',
            is_active  INTEGER DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS prompt_templates (
            agent_name TEXT PRIMARY KEY,
            content    TEXT NOT NULL,
            updated_by INTEGER,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Add new columns to users if they don't exist (SQLite-safe migration)
    new_cols = [
        ("api_key",           "TEXT DEFAULT ''"),
        ("preferred_model",   "TEXT DEFAULT ''"),
        ("temperature",       "REAL DEFAULT 0.2"),
        ("max_tokens",        "INTEGER DEFAULT 4096"),
        ("top_p",             "REAL DEFAULT 0.95"),
        ("monthly_tokens",    "INTEGER DEFAULT 0"),
        ("monthly_cost_usd",  "REAL DEFAULT 0.0"),
        ("avg_response_ms",   "INTEGER DEFAULT 0"),
        ("query_count",       "INTEGER DEFAULT 0"),
        ("openrouter_api_key",    "TEXT DEFAULT ''"),
        ("embedding_api_key",     "TEXT DEFAULT ''"),
        ("agent_model_config",    "TEXT DEFAULT NULL"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, definition in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

    # Migrate default_source_id → user_sources (one-time, only if user_sources is empty)
    if conn.execute("SELECT COUNT(*) FROM user_sources").fetchone()[0] == 0:
        conn.execute("""
            INSERT OR IGNORE INTO user_sources (user_id, source_id)
            SELECT id, default_source_id FROM users WHERE default_source_id IS NOT NULL
        """)

    # v0.2.1: 角色精简——viewer 合并入 analyst（保留 admin / analyst 二元）
    conn.execute("UPDATE users SET role='analyst' WHERE role='viewer'")

    # Seed admin account
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        from auth_utils import hash_password
        from config import DEFAULT_DB_HOST, DEFAULT_DB_PORT
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, doris_host, doris_port) "
            "VALUES (?, ?, '管理员', 'admin', ?, ?)",
            ("admin", hash_password("admin123"), DEFAULT_DB_HOST, DEFAULT_DB_PORT),
        )
        conn.execute("INSERT INTO semantic_layer (content) VALUES ('')")

    # v0.2.4: 一次性迁移 uploads.db → bi_agent.db（幂等：完成后重命名为 .merged）
    _migrate_uploads_db_once(conn)

    conn.commit()
    conn.close()


def _migrate_uploads_db_once(conn):
    """把老 uploads.db 里的所有用户上传表搬到主库；完成后把老文件改名为 .merged 以避免再次执行。

    幂等保障：① 老文件不存在就跳过；② 同名表已存在则跳过该表（保留主库现有数据，避免覆盖）；
    ③ 处理结束统一改名 → 下次启动直接命中"老文件不存在"。
    """
    import os
    from pathlib import Path

    old = Path(SQLITE_DB_PATH).parent / "uploads.db"
    if not old.exists():
        return

    try:
        conn.execute(f"ATTACH DATABASE '{old.as_posix()}' AS up")
        rows = conn.execute(
            "SELECT name FROM up.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        moved, skipped = 0, 0
        for r in rows:
            tbl = r[0]
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone()
            if exists:
                skipped += 1
                continue
            conn.execute(f'CREATE TABLE "{tbl}" AS SELECT * FROM up."{tbl}"')
            moved += 1
        conn.execute("DETACH DATABASE up")
        conn.commit()
        try:
            os.rename(old, old.with_suffix(".db.merged"))
        except OSError:
            pass
        if moved or skipped:
            print(f"[migration] uploads.db → bi_agent.db: moved={moved}, skipped={skipped}")
    except Exception as e:
        try:
            conn.execute("DETACH DATABASE up")
        except Exception:
            pass
        print(f"[migration] uploads.db merge skipped due to error: {e}")


# ── Users ──────────────────────────────────────────────────────────────

def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username, password_hash, display_name, role,
                doris_host, doris_port, doris_user, doris_password, doris_database):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO users "
            "(username, password_hash, display_name, role, doris_host, doris_port, doris_user, doris_password, doris_database) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (username, password_hash, display_name, role,
             doris_host, doris_port, doris_user, doris_password, doris_database),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def update_user(user_id, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    conn = get_conn()
    conn.execute(f"UPDATE users SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()


def update_user_usage(user_id, input_tokens, output_tokens, cost_usd, query_time_ms):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET "
        "monthly_tokens = monthly_tokens + ?, "
        "monthly_cost_usd = monthly_cost_usd + ?, "
        "query_count = query_count + 1, "
        "avg_response_ms = CAST((avg_response_ms * query_count + ?) / (query_count + 1) AS INTEGER) "
        "WHERE id=?",
        (input_tokens + output_tokens, cost_usd, query_time_ms, user_id),
    )
    conn.commit()
    conn.close()


def get_user_monthly_usage(user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT monthly_tokens, monthly_cost_usd, avg_response_ms, query_count FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_monthly_cost():
    conn = get_conn()
    row = conn.execute("SELECT SUM(monthly_cost_usd) AS total FROM users").fetchone()
    conn.close()
    return row["total"] or 0.0


# ── Conversations ──────────────────────────────────────────────────────

def create_conversation(user_id, title="新对话"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO conversations (user_id, title) VALUES (?,?)", (user_id, title)
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def list_conversations(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_conversation_title(conv_id, title):
    conn = get_conn()
    conn.execute(
        "UPDATE conversations SET title=?, updated_at=datetime('now','localtime') WHERE id=?",
        (title, conv_id),
    )
    conn.commit()
    conn.close()


def delete_conversation(conv_id):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()


# ── Messages ───────────────────────────────────────────────────────────

def save_message(conv_id, question, sql, explanation, confidence,
                 rows, db_error, cost_usd, input_tokens, output_tokens, retry_count):
    rows_json = json.dumps(rows, ensure_ascii=False, default=str)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO messages "
        "(conversation_id, question, sql_text, explanation, confidence, "
        "rows_json, db_error, cost_usd, input_tokens, output_tokens, retry_count) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (conv_id, question, sql, explanation, confidence,
         rows_json, db_error, cost_usd, input_tokens, output_tokens, retry_count),
    )
    mid = cur.lastrowid
    conn.execute(
        "UPDATE conversations SET updated_at=datetime('now','localtime') WHERE id=?",
        (conv_id,),
    )
    conn.commit()
    conn.close()
    return mid


def get_messages(conv_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
        (conv_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["rows"] = json.loads(d.get("rows_json") or "[]")
        result.append(d)
    return result


# ── Semantic layer ─────────────────────────────────────────────────────

def get_semantic_layer():
    conn = get_conn()
    row = conn.execute("SELECT content FROM semantic_layer LIMIT 1").fetchone()
    conn.close()
    return row["content"] if row else ""


def save_semantic_layer(content, updated_by):
    conn = get_conn()
    row = conn.execute("SELECT id FROM semantic_layer LIMIT 1").fetchone()
    if row:
        conn.execute(
            "UPDATE semantic_layer SET content=?, updated_by=?, updated_at=datetime('now','localtime') WHERE id=?",
            (content, updated_by, row["id"]),
        )
    else:
        conn.execute("INSERT INTO semantic_layer (content, updated_by) VALUES (?,?)", (content, updated_by))
    conn.commit()
    conn.close()


# ── Data sources ───────────────────────────────────────────────────────

def list_datasources():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM data_sources ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_datasource(source_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_datasource(user_id, name, description, db_host, db_port,
                      db_user, db_password, db_database, db_type="doris"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO data_sources "
        "(user_id, name, description, db_host, db_port, db_user, db_password, db_database, db_type) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, name, description, db_host, db_port, db_user, db_password, db_database, db_type),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def update_datasource(source_id, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [source_id]
    conn = get_conn()
    conn.execute(f"UPDATE data_sources SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()


def delete_datasource(source_id):
    conn = get_conn()
    conn.execute("DELETE FROM data_sources WHERE id=?", (source_id,))
    conn.commit()
    conn.close()


# ── User ↔ Data Source assignments ───────────────────────────────────────────

def set_user_sources(user_id: int, source_ids: list):
    conn = get_conn()
    conn.execute("DELETE FROM user_sources WHERE user_id=?", (user_id,))
    if source_ids:
        conn.executemany(
            "INSERT OR IGNORE INTO user_sources (user_id, source_id) VALUES (?,?)",
            [(user_id, sid) for sid in source_ids],
        )
    conn.commit()
    conn.close()


def get_user_source_ids(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT source_id FROM user_sources WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_user_source_ids() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT user_id, source_id FROM user_sources").fetchall()
    conn.close()
    result = {}
    for user_id, source_id in rows:
        result.setdefault(user_id, []).append(source_id)
    return result


# ── File uploads ──────────────────────────────────────────────────────────────

def create_file_upload(user_id, filename, table_name, row_count, columns):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO file_uploads (user_id, filename, table_name, row_count, columns_json) VALUES (?,?,?,?,?)",
        (user_id, filename, table_name, row_count, json.dumps(columns, ensure_ascii=False)),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def list_file_uploads(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM file_uploads WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["columns"] = json.loads(d.get("columns_json") or "[]")
        result.append(d)
    return result


def get_file_upload(upload_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM file_uploads WHERE id=?", (upload_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["columns"] = json.loads(d.get("columns_json") or "[]")
    return d


def delete_file_upload(upload_id):
    conn = get_conn()
    conn.execute("DELETE FROM file_uploads WHERE id=?", (upload_id,))
    conn.commit()
    conn.close()


# ── Knowledge docs ────────────────────────────────────────────────────────────

def create_knowledge_doc(name: str, filename: str, chunk_count: int) -> int:
    conn = get_conn()
    cur  = conn.execute(
        "INSERT INTO knowledge_docs (name, filename, chunk_count) VALUES (?,?,?)",
        (name, filename, chunk_count),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def list_knowledge_docs() -> list:
    conn  = get_conn()
    rows  = conn.execute("SELECT * FROM knowledge_docs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_knowledge_doc(doc_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM doc_chunks WHERE doc_id=?", (doc_id,))
    conn.execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()


def save_doc_chunks(doc_id: int, chunks: list, embeddings: list):
    """embeddings[i] 为 bytes blob 或 None。"""
    conn = get_conn()
    conn.executemany(
        "INSERT INTO doc_chunks (doc_id, chunk_text, embedding_blob) VALUES (?,?,?)",
        [(doc_id, chunks[i], embeddings[i]) for i in range(len(chunks))],
    )
    conn.commit()
    conn.close()


def list_doc_chunks() -> list:
    conn  = get_conn()
    rows  = conn.execute("SELECT chunk_text, embedding_blob FROM doc_chunks").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Model settings ─────────────────────────────────────────────────────

def get_model_settings():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM model_settings").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_model_enabled(model_key, enabled):
    conn = get_conn()
    conn.execute(
        "INSERT INTO model_settings (model_key, enabled) VALUES (?,?) "
        "ON CONFLICT(model_key) DO UPDATE SET enabled=?, updated_at=datetime('now','localtime')",
        (model_key, enabled, enabled),
    )
    conn.commit()
    conn.close()


def set_default_model(model_key):
    conn = get_conn()
    conn.execute("UPDATE model_settings SET is_default=0")
    conn.execute(
        "INSERT INTO model_settings (model_key, enabled, is_default) VALUES (?,1,1) "
        "ON CONFLICT(model_key) DO UPDATE SET is_default=1, updated_at=datetime('now','localtime')",
        (model_key,),
    )
    conn.commit()
    conn.close()


# ── Agent model config ─────────────────────────────────────────────────

def get_agent_model_config() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key='agent_model_config'").fetchone()
    conn.close()
    if row and row["value"]:
        try:
            return json.loads(row["value"])
        except Exception:
            pass
    return {}


def set_agent_model_config(config: dict):
    v = json.dumps(config, ensure_ascii=False)
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('agent_model_config', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now','localtime')",
        (v, v),
    )
    conn.commit()
    conn.close()


# ── Per-user agent model config ────────────────────────────────────────

def get_user_agent_model_config(user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT agent_model_config FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if row and row["agent_model_config"]:
        try:
            return json.loads(row["agent_model_config"])
        except Exception:
            pass
    return {}


def set_user_agent_model_config(user_id: int, config: dict):
    v = json.dumps(config, ensure_ascii=False)
    conn = get_conn()
    conn.execute("UPDATE users SET agent_model_config=? WHERE id=?", (v, user_id))
    conn.commit()
    conn.close()


# ── Generic app_settings ───────────────────────────────────────────────

def get_app_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_app_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now','localtime')",
        (key, value, value),
    )
    conn.commit()
    conn.close()


# ── Few-shot examples (DB-backed) ──────────────────────────────────────

def list_few_shots(only_active: bool = False) -> list:
    conn = get_conn()
    if only_active:
        rows = conn.execute(
            "SELECT * FROM few_shots WHERE is_active=1 ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM few_shots ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_few_shot(question: str, sql: str, type_: str = "", is_active: int = 1) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO few_shots (question, sql, type, is_active) VALUES (?,?,?,?)",
        (question, sql, type_ or "", 1 if is_active else 0),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_few_shot(fid: int, **kwargs):
    if not kwargs:
        return
    allowed = {"question", "sql", "type", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields) + ", updated_at=datetime('now','localtime')"
    values = list(fields.values()) + [fid]
    conn = get_conn()
    conn.execute(f"UPDATE few_shots SET {set_clause} WHERE id=?", values)
    conn.commit()
    conn.close()


def delete_few_shot(fid: int):
    conn = get_conn()
    conn.execute("DELETE FROM few_shots WHERE id=?", (fid,))
    conn.commit()
    conn.close()


def bulk_insert_few_shots(items: list) -> int:
    """items: list of {question, sql, type?, is_active?}; returns inserted count."""
    if not items:
        return 0
    conn = get_conn()
    conn.executemany(
        "INSERT INTO few_shots (question, sql, type, is_active) VALUES (?,?,?,?)",
        [
            (it.get("question", ""), it.get("sql", ""),
             it.get("type", "") or "", 1 if it.get("is_active", 1) else 0)
            for it in items if it.get("question") and it.get("sql")
        ],
    )
    conn.commit()
    conn.close()
    return len(items)


# ── Prompt templates (per-agent system prompt overrides) ───────────────

def list_prompt_templates() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM prompt_templates ORDER BY agent_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prompt_template(agent_name: str) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT content FROM prompt_templates WHERE agent_name=?", (agent_name,)
    ).fetchone()
    conn.close()
    return row["content"] if row and row["content"] else ""


def set_prompt_template(agent_name: str, content: str, updated_by: int = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO prompt_templates (agent_name, content, updated_by) VALUES (?,?,?) "
        "ON CONFLICT(agent_name) DO UPDATE SET content=?, updated_by=?, "
        "updated_at=datetime('now','localtime')",
        (agent_name, content, updated_by, content, updated_by),
    )
    conn.commit()
    conn.close()


def delete_prompt_template(agent_name: str):
    conn = get_conn()
    conn.execute("DELETE FROM prompt_templates WHERE agent_name=?", (agent_name,))
    conn.commit()
    conn.close()
