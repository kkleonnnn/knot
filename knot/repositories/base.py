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
    # 形态：{"base_url": "https://api.example.com", "auth_header": "Authorization",
    #        "auth_value": "<token>", "timeout_sec": 5}
    # db_type 现有 default='doris' → 加 'http' 选项
    ds_cols = {row[1] for row in conn.execute("PRAGMA table_info(data_sources)").fetchall()}
    if "http_config" not in ds_cols:
        conn.execute("ALTER TABLE data_sources ADD COLUMN http_config TEXT DEFAULT ''")

    # v0.6.2.0 TOTP 2FA — users 表加 4 列（R-PB-B1-1/8/13）
    # totp_secret: Fernet 加密 enc_v1: 前缀（仅 SQLite knot.db；不涉 Doris）
    # totp_enrolled_at / totp_last_used_at: 时间戳（5 次/月 警报基线）
    # token_version: JWT 吊销机制（R-PB-B1-13 — reset/change_password 时 +1 → 旧 JWT 失效）
    users_cols_v062 = [
        ("totp_secret",       "TEXT"),
        ("totp_enrolled_at",  "TEXT"),
        ("totp_last_used_at", "TEXT"),
        ("token_version",     "INTEGER NOT NULL DEFAULT 1"),
    ]
    users_cols_after = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, definition in users_cols_v062:
        if col not in users_cols_after:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

    # v0.6.2.0 TOTP recovery codes 表（R-PB-B1-2 不锁死兜底）
    # code_hash: bcrypt（与 password_hash 同；明文不留 DB）
    # used_at NULL = 未使用；INSERT 在 enroll 完成时（R-PB-B1-7 强制下载之后）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS totp_recovery_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            code_hash  TEXT    NOT NULL,
            used_at    TEXT,
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_totp_recovery_user_unused
            ON totp_recovery_codes(user_id) WHERE used_at IS NULL
    """)

    # ── v0.6.2.5 段 4 (A1): single-tenant 多 catalog 切换 — 迁移地基 ─────────────
    # OOS-1 死线（R-PB-A1-1）：catalogs 表 + users.active_catalog_id 严禁 tenant_id/project_id；
    #   catalog_id = 语义层水平切分（per-user active catalog）≠ 租户数据隔离。
    # users.active_catalog_id：每用户 active catalog（NULL → 兜底 catalog id=1）
    users_cols_v0625 = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "active_catalog_id" not in users_cols_v0625:
        conn.execute("ALTER TABLE users ADD COLUMN active_catalog_id INTEGER")

    # audit_log.catalog_id：R-PB-A1-5 ③ — 操作关联的 catalog（NULL = 无关 catalog 的操作）
    audit_cols_v0625 = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    if "catalog_id" not in audit_cols_v0625:
        conn.execute("ALTER TABLE audit_log ADD COLUMN catalog_id INTEGER")

    # v0.7.6 semantic_query_audit.restored_from_audit_id：append-only 恢复来源版本 id（R-SL-60；
    #   NULL = 原始/修正/near-miss；非 NULL = 「采纳」恢复行的源版本 audit id）。幂等 ADD COLUMN。
    sqa_cols_v076 = {row[1] for row in conn.execute("PRAGMA table_info(semantic_query_audit)").fetchall()}
    if "restored_from_audit_id" not in sqa_cols_v076:
        conn.execute("ALTER TABLE semantic_query_audit ADD COLUMN restored_from_audit_id INTEGER")

    # v0.7.17 metrics.date_column：时间窗注入列名（显式优先；空=按维度名 regex 推断）。
    #   存量 metric ADD COLUMN 得空串 = 未声明 = regex fallback（不破存量编译）。幂等 ADD COLUMN。
    metrics_cols_v0717 = {row[1] for row in conn.execute("PRAGMA table_info(metrics)").fetchall()}
    if "date_column" not in metrics_cols_v0717:
        conn.execute("ALTER TABLE metrics ADD COLUMN date_column TEXT DEFAULT ''")

    # v0.7.25 metrics.unit：值单位/格式（percentage=值×100+%，空=默认 toLocaleString）。幂等 ADD COLUMN；
    #   存量 metric 得空串 = 默认渲染（不破存量）。R1：percentage 值须 0-1 小数（防 ×100 双缩放）。
    if "unit" not in metrics_cols_v0717:
        conn.execute("ALTER TABLE metrics ADD COLUMN unit TEXT DEFAULT ''")

    # v0.7.27 catalogs.field_labels：维度中文标签 {列名:中文} JSON（镜像 relations；存量 catalog
    #   ADD COLUMN 得空串 → 解析 {} → _semantic_display_meta merge no-op → byte-equal 不破存量）。幂等 ADD COLUMN。
    catalogs_cols_v0727 = {row[1] for row in conn.execute("PRAGMA table_info(catalogs)").fetchall()}
    if "field_labels" not in catalogs_cols_v0727:
        conn.execute("ALTER TABLE catalogs ADD COLUMN field_labels TEXT DEFAULT ''")

    # catalogs 表 seed — 现有 app_settings 4-key catalog 内容搬为 catalog id=1（byte-equal copy）
    # 幂等：仅 catalogs 空时执行；app_settings 空（fresh install）→ 空内容行
    #   （与现状一致 — catalog_loader 内容为空时回退 file 默认；commit 3 reload 改读本表）
    if conn.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0] == 0:
        _cat_kv = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN "
                "('catalog.tables', 'catalog.lexicon', 'catalog.business_rules', 'catalog.relations')"
            ).fetchall()
        }
        conn.execute(
            "INSERT INTO catalogs (id, name, description, tables, lexicon, business_rules, relations) "
            "VALUES (1, '默认 Catalog', '', ?, ?, ?, ?)",
            (
                _cat_kv.get("catalog.tables", ""),
                _cat_kv.get("catalog.lexicon", ""),
                _cat_kv.get("catalog.business_rules", ""),
                _cat_kv.get("catalog.relations", ""),
            ),
        )

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

    # v0.6.5.4 OR-only 孤儿清理（幂等 · 同步 DML 非 create_task — 不重蹈 v0.6.5.3 startup race）：
    # cfg.MODELS 删 6 直连 + 死 OR 后，现存 model_settings 行若引用被删 key（admin 曾启用/设默认）
    # → admin 模型页迭代不到（孤儿）。DELETE 清孤儿；空表 no-op。
    # 兜底默认：仅当 model_settings *非空*（admin 配过）且无 is_default 时，设 OR 默认 —— fresh/test
    # DB（model_settings 空，c==0）确定性跳过，绝不给 test DB 加行（守 v0.6.5.3 测试隔离）。
    _orphan_keys = (
        "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "gpt-4o-mini", "gpt-4o",
        "gemini-2.0-flash", "deepseek-chat", "google/gemini-2.0-flash-001",
    )
    conn.execute(
        f"DELETE FROM model_settings WHERE model_key IN ({','.join('?' * len(_orphan_keys))})",
        _orphan_keys,
    )
    _ms = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(is_default), 0) d FROM model_settings").fetchone()
    if _ms[0] > 0 and _ms[1] == 0:
        conn.execute(
            "INSERT INTO model_settings (model_key, enabled, is_default) VALUES ('anthropic/claude-haiku-4.5', 1, 1) "
            "ON CONFLICT(model_key) DO UPDATE SET is_default=1"
        )

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
