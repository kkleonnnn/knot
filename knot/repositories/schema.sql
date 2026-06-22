-- knot.repositories.schema — DDL 集中式（v0.3.0+）
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
    -- v0.6.0.20: admin 默认账号 admin/admin123 强制改密守护（1.0 公测前必清的安全债）
    -- 0=已改 / 1=必须改密；admin seed 时设 1，change-password 端点改 0
    must_change_password INTEGER DEFAULT 0,
    -- v0.6.2.0 TOTP 2FA（R-PB-B1-1/8 Fernet enc_v1: 前缀 — 仅 SQLite knot.db）
    totp_secret       TEXT,                              -- Fernet 加密；NULL = 未 enroll
    totp_enrolled_at  TEXT,                              -- enroll 完成时间；NULL = 未 enroll
    totp_last_used_at TEXT,                              -- 最近一次验证成功时间（5 次/月 警报基线）
    -- v0.6.2.0 R-PB-B1-13 JWT 吊销真空期防御（reset/change_password 时 +1 → 旧 JWT 失效）
    token_version     INTEGER NOT NULL DEFAULT 1,
    -- v0.6.2.5 段 4 (A1): 每用户 active catalog（per-user 切换 — R-PB-A1-1 OOS-1 死线：
    -- catalog_id = 语义层水平切分 ≠ 租户隔离；NULL → 兜底 catalog id=1）
    active_catalog_id INTEGER,
    created_at     TEXT    DEFAULT (datetime('now','localtime'))
);

-- v0.6.2.0 TOTP recovery codes（R-PB-B1-2 不锁死兜底；R-PB-B1-11 user.totp.recovery_code_used audit）
-- code_hash: bcrypt hash（与 password_hash 同精神 — 单向；明文不留 DB）
-- used_at NULL = 未使用；R-PB-B1-7 强制下载后 enroll 完成才 INSERT
CREATE TABLE IF NOT EXISTS totp_recovery_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    code_hash  TEXT    NOT NULL,
    used_at    TEXT,
    created_at TEXT    DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_totp_recovery_user_unused
    ON totp_recovery_codes(user_id) WHERE used_at IS NULL;

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
    -- v0.6.1.4 OVERRIDE #4: db_type='http' 时下列 db_* 字段可为空字符串
    db_host     TEXT    DEFAULT '',
    db_port     INTEGER DEFAULT 9030,
    db_user     TEXT    DEFAULT '',
    db_password TEXT    DEFAULT '',
    db_database TEXT    DEFAULT '',
    db_type     TEXT    DEFAULT 'doris',  -- doris / mysql / http
    -- v0.6.1.4: HTTP 类型数据源专用配置 (JSON 字符串, Fernet 加密入库)
    -- 形态: {"base_url","auth_header","auth_value","allowed_hosts","timeout_sec"}
    http_config TEXT    DEFAULT '',
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

-- v0.6.2.5 段 4 (A1): single-tenant 多 catalog 切换
-- ⚠️ OOS-1 死线（R-PB-A1-1 守护者强化）：严禁 tenant_id / project_id 列 —
--    catalog_id = 语义层水平切分（admin/user 切 active catalog）≠ 租户数据隔离；
--    数据库连接共享（engine_cache key 不动）→ 非多租户隔离架构。真多租户隔离推 v1.x+。
-- 取代 app_settings 4-key 全局单例（catalog.tables/lexicon/business_rules/relations）；
-- per-user active 由 users.active_catalog_id 解析（本表不设 is_active 全局标记）。
-- 4 字段 JSON 形状与 app_settings 4-key byte-equal（R-PB-A1-7）。
CREATE TABLE IF NOT EXISTS catalogs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    description    TEXT    DEFAULT '',
    tables         TEXT    DEFAULT '',   -- JSON list（对应 catalog.tables）
    lexicon        TEXT    DEFAULT '',   -- JSON dict（对应 catalog.lexicon）
    business_rules TEXT    DEFAULT '',   -- text（对应 catalog.business_rules）
    relations      TEXT    DEFAULT '',   -- JSON list（对应 catalog.relations）
    created_at     TEXT    DEFAULT (datetime('now','localtime')),
    updated_at     TEXT    DEFAULT (datetime('now','localtime'))
);

-- v0.7.0 C1 语义层第一刀：指标注册表（单一真源指标定义）
-- ⚠️ OOS-1 死线 sustained：metric 归 catalog_id（语义层水平切分）；严禁 tenant_id / project_id 列。
--    catalog_id = 逻辑外键（soft ref → catalogs(id)，无 enforced FK；与 users.active_catalog_id /
--    audit_log.catalog_id 同为裸 INTEGER，项目未启 PRAGMA foreign_keys）。
-- lineage：派生指标依赖（JSON list）；v0.7.0 仅 inert 存储，自引用/循环 DFS 校验留 v0.7.1（编译时）。
CREATE TABLE IF NOT EXISTS metrics (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id         INTEGER NOT NULL DEFAULT 1,  -- soft ref catalogs(id)；OOS-1 水平切分非租户
    name               TEXT    NOT NULL,            -- 唯一标识（per catalog_id 唯一）
    display            TEXT    DEFAULT '',           -- 中文展示名
    aliases            TEXT    DEFAULT '',           -- JSON list（v0.7.1+ 喂 LEXICON / clarifier）
    caliber            TEXT    NOT NULL,             -- 口径表达式 SUM(o.pay_amount)（非密 — R-SL-5）
    base_object        TEXT    DEFAULT '',           -- 挂的对象/表（v0.7.2 对象层消费）
    filters            TEXT    DEFAULT '',           -- JSON list 口径内置过滤（非密）
    dimensions         TEXT    DEFAULT '',           -- JSON list 可下钻维度
    lineage            TEXT    DEFAULT '',           -- JSON list 派生依赖（inert；v0.7.1 编译校验）
    freshness_lag_days INTEGER DEFAULT 1,            -- 复用 time_resolver D-1 默认
    enabled            INTEGER DEFAULT 1,            -- 软开关
    created_at         TEXT    DEFAULT (datetime('now','localtime')),
    updated_at         TEXT    DEFAULT (datetime('now','localtime')),
    UNIQUE (catalog_id, name)                        -- per-catalog 指标名唯一
);
CREATE INDEX IF NOT EXISTS idx_metrics_catalog ON metrics(catalog_id);

-- v0.7.3 语义层 LogicForm 审计侧表（message_id 软 FK；messages 0 ALTER — 守护者侧表裁定）。
-- 仅语义路径 / near-miss 行（多数 message 是 LLM 路径 → 本表小，不恶化 messages R-S6 ≥24 列）。
-- ⚠️ R-SL-40：catalog_id = LogicForm 解析时 active catalog（messages 无 catalog_id；catalog 是 ContextVar
--    临时解析从不落 message → 审计渲染 / 修正 re-run 须存当时 catalog）。OOS-1 soft ref，0 tenant_id。
CREATE TABLE IF NOT EXISTS semantic_query_audit (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id           INTEGER NOT NULL,            -- soft FK → messages(id)
    catalog_id           INTEGER NOT NULL DEFAULT 1,  -- R-SL-40 解析时 active catalog（OOS-1 soft ref）
    logicform_json       TEXT    DEFAULT '',          -- canonical_json（命中）；near-miss 也存（诊断）
    compile_error_reason TEXT    DEFAULT '',          -- near-miss CompileError 原因；命中为空
    is_corrected         INTEGER DEFAULT 0,           -- admin 修正产生的行标 1（F4）
    parent_message_id    INTEGER,                     -- 修正链：指向原 message（审计血缘）
    created_at           TEXT    DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_sqa_message ON semantic_query_audit(message_id);
CREATE INDEX IF NOT EXISTS idx_sqa_catalog ON semantic_query_audit(catalog_id);

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

-- v0.4.3: 预算配置（资深 R-16 决议：global / user / agent_kind 同表 DRY）
-- UNIQUE 防重复 — 服务于 R-18 幂等 INSERT OR REPLACE
CREATE TABLE IF NOT EXISTS budgets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type      TEXT    NOT NULL,             -- 'user' | 'agent_kind' | 'global'
    scope_value     TEXT    NOT NULL,             -- user_id (str) / agent_kind / 'all'
    budget_type     TEXT    NOT NULL,             -- 'monthly_cost_usd' | 'monthly_tokens' | 'per_call_cost_usd'
    threshold       REAL    NOT NULL,
    action          TEXT    NOT NULL DEFAULT 'warn',  -- 'warn' | 'block'（block 仅 agent_kind/per_call）
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    DEFAULT (datetime('now','localtime')),
    UNIQUE (scope_type, scope_value, budget_type)
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

-- v0.4.6: 审计日志（who-did-what）— INSERT-only（DELETE 仅 purge 脚本入口）
-- R-58: client_ip / user_agent 独立列；R-54: actor_name 冗余快照（用户被删审计仍可读）
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id      INTEGER,
    actor_role    TEXT,
    actor_name    TEXT,
    action        TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   TEXT,
    success       INTEGER DEFAULT 1,
    detail_json   TEXT DEFAULT '',
    client_ip     TEXT,
    user_agent    TEXT,
    request_id    TEXT,
    -- v0.6.2.5 段 4 (R-PB-A1-5 ③): 操作关联的 catalog（NULL = 无关 catalog 的操作）
    catalog_id    INTEGER,
    created_at    TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_log(actor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_log(action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);

-- v0.6.0.6 F-D: OpenRouter live catalog 缓存（admin "同步 OR" 按钮 UPSERT）
-- 设计：admin 主动 fetch OR API → 落 model_catalog_live；前端可对比 MODELS dict 看差异
-- 不影响业务路径（业务仍读 MODELS dict）；纯审计/参考用途
CREATE TABLE IF NOT EXISTS model_catalog_live (
    model_id       TEXT PRIMARY KEY,
    context_length INTEGER,
    input_price    REAL,
    output_price   REAL,
    raw_json       TEXT,           -- 完整 OR 行 JSON 存档（防字段未来扩展）
    fetched_at     TEXT DEFAULT (datetime('now','localtime'))
);

-- v0.6.0.4 F-B: 前端 JS 错误上报（onerror + onunhandledrejection 自动捕获）
-- M-B2 PII：message + stack 落库前由后端 _scrub 链脱敏（复用 audit_service._scrub）
-- 守护者 P-2 模式：dedupe by hash 由前端 1h cooldown + 1min 全局 cap 5 防爆
CREATE TABLE IF NOT EXISTS frontend_errors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,            -- 允许 NULL（未登录页 JS 错也想捕获）
    message      TEXT    NOT NULL,
    stack        TEXT    DEFAULT '',
    url          TEXT    DEFAULT '',
    user_agent   TEXT    DEFAULT '',
    error_hash   TEXT,                -- 前端算的 hash(stack first 10 lines + message) — admin 看趋势
    created_at   TEXT    DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_fe_errors_hash_time ON frontend_errors(error_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_fe_errors_time      ON frontend_errors(created_at);

-- v0.6.0.3 F-A: 用户对每条 assistant 回答的 +1/-1 反馈 + 可选评论
-- UNIQUE (message_id, user_id) — 同用户对同消息幂等覆盖；admin 全局可读
CREATE TABLE IF NOT EXISTS message_feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    score        INTEGER NOT NULL,  -- +1 (good) or -1 (bad)
    comment      TEXT    DEFAULT '',
    created_at   TEXT    DEFAULT (datetime('now','localtime')),
    UNIQUE (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_message ON message_feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_score_time ON message_feedback(score, created_at);
