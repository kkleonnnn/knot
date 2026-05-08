-- bi_agent.repositories.schema — DDL 集中式（v0.3.0）
-- 任何新表/新列都在此添加；新增列在 base.py 的 ALTER TABLE 兼容块同步。

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
    intent          TEXT,
    -- v0.4.2: 成本归因分桶（资深 Stage 2 列扩展决议；Stage 4 拍板 fix_sql 独立 agent_kind）
    agent_kind         TEXT    NOT NULL DEFAULT 'legacy',  -- clarifier|sql_planner|fix_sql|presenter|legacy
    clarifier_cost     REAL    DEFAULT 0,
    sql_planner_cost   REAL    DEFAULT 0,
    fix_sql_cost       REAL    DEFAULT 0,
    presenter_cost     REAL    DEFAULT 0,
    clarifier_tokens   INTEGER DEFAULT 0,
    sql_planner_tokens INTEGER DEFAULT 0,
    fix_sql_tokens     INTEGER DEFAULT 0,
    presenter_tokens   INTEGER DEFAULT 0,
    recovery_attempt   INTEGER DEFAULT 0,                  -- R-14：含 fan-out reject + fix_sql retry 计数
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

-- v0.4.1: 报表沉淀。完全去耦合的快照（无硬 FK）— 上游 conversation/message/datasource
-- 删除时本表行不级联，source_message_id / data_source_id 变 dangling 是预期。
CREATE TABLE IF NOT EXISTS saved_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    source_message_id   INTEGER,
    data_source_id      INTEGER,
    title               TEXT    NOT NULL,
    question            TEXT,
    sql_text            TEXT    NOT NULL,
    intent              TEXT,
    display_hint        TEXT,
    pin_note            TEXT,
    last_run_at         TEXT,
    last_run_rows_json  TEXT,
    last_run_truncated  INTEGER DEFAULT 0,
    last_run_ms         INTEGER DEFAULT 0,
    pinned_at           TEXT    DEFAULT (datetime('now','localtime')),
    UNIQUE (user_id, source_message_id)
);
