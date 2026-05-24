"""knot.repositories.base — connection helper + init_db。

WAL mode、Row factory、check_same_thread=False 与原 persistence 等价。
init_db() 集中执行 schema + 历史 ALTER TABLE 兼容迁移。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from knot.config import SQLITE_DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def init_db():
    """启动期建表 + 历史兼容迁移 + seed admin。"""
    conn = get_conn()
    conn.executescript(_SCHEMA_SQL)

    # users 表新列兼容（SQLite-safe ALTER）
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
        # v0.6.0.20: admin 默认账号 admin/admin123 强制改密守护（1.0 公测前必清的安全债）
        # SQLite bool surrogate: 0=已改 / 1=必须改密；seed 时设 1，change-password 端点改 0
        # 老数据列 ALTER 后默认 0（已存在的用户视为已正常配置，无须强制改密）
        ("must_change_password",  "INTEGER DEFAULT 0"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, definition in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

    # v0.4.0: messages.intent — Clarifier 输出的 7 类意图，老消息为 NULL
    msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "intent" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN intent TEXT")

    # v0.4.2: 成本归因分桶 + recovery_attempt 列（R-S6 警告：messages 列数 ≥ 24，
    # v0.4.5+ 需评估迁移工具引入）
    msg_new_cols_v042 = [
        # agent_kind 不在动态加列里 — 必须在 ALTER 后立刻 UPDATE 老行为 'legacy'，
        # 但 SQLite 不支持 ALTER ... ADD COLUMN ... NOT NULL DEFAULT 在已有行上同步生效。
        # 解法：先加可空列 + 立即 UPDATE 全表为 'legacy' + 由 save_message 守护新写入。
        ("agent_kind",         "TEXT DEFAULT 'legacy'"),
        ("clarifier_cost",     "REAL DEFAULT 0"),
        ("sql_planner_cost",   "REAL DEFAULT 0"),
        ("fix_sql_cost",       "REAL DEFAULT 0"),
        ("presenter_cost",     "REAL DEFAULT 0"),
        ("clarifier_tokens",   "INTEGER DEFAULT 0"),
        ("sql_planner_tokens", "INTEGER DEFAULT 0"),
        ("fix_sql_tokens",     "INTEGER DEFAULT 0"),
        ("presenter_tokens",   "INTEGER DEFAULT 0"),
        ("recovery_attempt",   "INTEGER DEFAULT 0"),
    ]
    msg_cols_after_intent = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    for col, definition in msg_new_cols_v042:
        if col not in msg_cols_after_intent:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {definition}")
    # R-S6 / Stage 3-A 保险：所有老行（agent_kind 为 NULL）显式回填 'legacy'
    conn.execute("UPDATE messages SET agent_kind='legacy' WHERE agent_kind IS NULL")

    # v0.6.1.0: messages.latency_ms — 端到端响应延迟（毫秒），用于 admin 内测指标屏 P95
    # NULL 允许（老消息无此数据；P95 计算时 WHERE latency_ms IS NOT NULL 过滤）
    if "latency_ms" not in msg_cols_after_intent:
        conn.execute("ALTER TABLE messages ADD COLUMN latency_ms INTEGER")

    # v0.6.1.4 OVERRIDE #4: data_sources.http_config — HTTP 类型数据源专用配置
    # JSON 字符串，Fernet 加密（含 auth_value 敏感字段）
    # 形态：{"base_url": "...", "auth_header": "key", "auth_value": "bitda",
    #        "allowed_hosts": "host1,host2", "timeout_sec": 5}
    # db_type 现有 default='doris' → 加 'http' 选项
    ds_cols = {row[1] for row in conn.execute("PRAGMA table_info(data_sources)").fetchall()}
    if "http_config" not in ds_cols:
        conn.execute("ALTER TABLE data_sources ADD COLUMN http_config TEXT DEFAULT ''")

    # default_source_id → user_sources（一次性，user_sources 为空时执行）
    if conn.execute("SELECT COUNT(*) FROM user_sources").fetchone()[0] == 0:
        conn.execute("""
            INSERT OR IGNORE INTO user_sources (user_id, source_id)
            SELECT id, default_source_id FROM users WHERE default_source_id IS NOT NULL
        """)

    # v0.2.1: 角色精简 viewer → analyst
    conn.execute("UPDATE users SET role='analyst' WHERE role='viewer'")

    # Seed admin（v0.3.1：通过 bcrypt 直接哈希避免 repos→services 反向依赖）
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        import bcrypt

        from knot.config import DEFAULT_DB_HOST, DEFAULT_DB_PORT
        seed_pwd = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
        # v0.6.0.20: seed admin 必须改密（must_change_password=1）— 默认密码 admin123 是已知公开值
        # 首登 login → must_change_password=1 → 前端 ForceChangePassword 模态 → POST /api/auth/change-password → 0
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, doris_host, doris_port, must_change_password) "
            "VALUES (?, ?, '管理员', 'admin', ?, ?, 1)",
            ("admin", seed_pwd, DEFAULT_DB_HOST, DEFAULT_DB_PORT),
        )
        conn.execute("INSERT INTO semantic_layer (content) VALUES ('')")

    # v0.2.4: uploads.db 一次性合并入主 DB（幂等）
    _migrate_uploads_db_once(conn)

    conn.commit()
    conn.close()


def _migrate_uploads_db_once(conn):
    """把老 uploads.db 里的所有用户上传表搬到主库；完成后改名 .merged 防再次执行。"""
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
            print(f"[migration] uploads.db merged into main DB: moved={moved}, skipped={skipped}")
    except Exception as e:
        try:
            conn.execute("DETACH DATABASE up")
        except Exception:
            pass
        print(f"[migration] uploads.db merge skipped due to error: {e}")
