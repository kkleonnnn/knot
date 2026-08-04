-- knot/repositories/platform_schema.sql — 平台库(platform.db) schema（v0.9.0 仅 tenants 表）。
--
-- OOS-1v2：租户归属列仅允许存在于平台库（tenants 等平台元数据表）；租户库内严禁 tenant_id 列
-- （行级租户列对 LogicForm 编译器 fail-open）。多租户隔离靠 per-tenant SQLite 文件边界（C 方案 fail-closed）。
--
-- 未来平台表预留（v0.9.0 只留注释不建表 — byte-equal 最大化，平台库最小起步）：
--   user_directory   [0.1] 平台级用户 → 租户路由（JWT tid 解析 · login 定位库）
--   platform_admins  [0.1] 平台管理员（platform_admin vs tenant_admin 鉴权拆分）
--   platform_audit   [0.4] 平台侧动作审计（租户开通/停用）+ 跨租户聚合只读视图

CREATE TABLE IF NOT EXISTS tenants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',   -- 'active' | 'suspended'
    db_dir      TEXT    NOT NULL,                    -- 相对 SQLITE_DB_PATH.parent 解析：'tenants/1'(生产) / '.'(测试 anchor 本身)
    created_at  TEXT    DEFAULT (datetime('now','localtime')),
    -- v0.9.7 B-3 ③（egress 租户域化）：本租户允许出网的 host 集，逗号分隔。**部署方控制**（无任何写端点 —— v0.9.5 E2
    -- 刻意零平台写操作 ⇒ 唯一配置途径是直接 UPDATE，SQL 原文见 DEPLOY.md「多租户运维门」）。
    -- ⚠️ 三态语义（解析判据必须是 `is None`，不得用真值判断 —— 见 adapters/http/url_allowlist.get_allowed_hosts）：
    --   NULL = **未配置** ⇒ 起源租户回退 env KNOT_HTTP_ALLOWED_HOSTS（+启动 WARN）；非起源租户全拒绝
    --   ''   = **已配置为空** ⇒ 部署方明确表达「禁」⇒ 全拒绝，**起源租户也不回退 env**
    --   非空 = 该 host 集本身（**永不与 env 或其他租户取交集/并集** —— 取交集会「为给客租户开权而放宽起源租户」）
    allowed_http_hosts TEXT,
    -- v0.9.8：平台元数据变更时间线（此前缺 ⇒「谁改了 db_dir」无时间线）。
    -- 由 `tenant_repo.update_tenant` 这个**单一写口** stamp；直接 UPDATE 绕过它则不 stamp（已诚实登记）。
    updated_at  TEXT
);

-- ─────────────────────────────────────────────────────────────────────────────
-- v0.9.8 platform_audit —— **平台侧动作留痕**（R-T-GATE 清单 R7；解锁 R-10 的阻塞理由）
--
-- 为什么必须是**平台库**里的表：`audit_service.log` → `audit_repo.insert` → `get_conn` = **租户库**，
-- 而平台动作（建/停租户、改 db_dir）**没有租户库可写** —— 这正是 v0.9.5 E2「不引入平台写操作」
-- 的理由原文。⇒ 给它一个落点。
--
-- ⚠️ **append-only**（D7-④ 哨兵强制）：只许 INSERT + SELECT。
--   全仓禁 `UPDATE platform_audit` / `DELETE FROM platform_audit` —— 审计是**只可追加的证据**，
--   不是可编辑的记录。将来若要做清理（已登记 backlog），必须是一次**显式、被评审**的改动。
--
-- ⚠️ **写入必须与被记录的动作同事务**（D3）：`insert(conn, …)` 由调用方注入连接且**不 commit**
--   ⇒「审计写失败」不是独立事件、与「动作失败」是同一件事 ⇒ 不存在「动作发生了但没记」
--   或「记了但没发生」，也**不需要**在 raise 与吞之间选一条策略。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    -- actor 口径：'system:boot'（启动期 seed，无人参与）/ 'cli:<显式传入>'（P2 的 CLI 强制 --actor）/ NULL（未知）
    -- ⛔ **严禁**用容器 `whoami` 充当 actor —— `kubectl exec` 下它 = root/app user
    --    ⇒ 把「谁」记成 root ⇒ 本表的价值命题（「谁改了 db_dir」）当场落空。
    -- 单列（而非租户审计的 actor_id/actor_role/actor_name 三列）是**刻意的**：平台动作**无登录用户**
    --    ⇒ 三列里两列恒 NULL。写明理由是为了防将来「顺手统一成三列」而使 actor_role 恒空像 bug。
    actor        TEXT,
    action       TEXT    NOT NULL,   -- models/platform_audit.PlatformAuditAction（Literal，精确集合守护）
    tenant_id    INTEGER,            -- 动作的对象租户（NULL = 非租户维动作）
    -- ⚠️ slug 冗余是**刻意的快照**：审计的价值在**事后**可读；只存 tenant_id 的话，
    --    租户被删/改名后那条记录就退化成一个无意义的数字。**审计记录必须自解释。**
    tenant_slug  TEXT,
    success      INTEGER NOT NULL DEFAULT 1,
    -- detail_json：变更详情（如 db_dir 从什么改成什么）。⚠️ **严禁写入凭据 / env 值 / allowlist 内容**
    --    —— D7-② AST 哨兵守它，而**该哨兵同时是 `GET /api/platform/audit` 的承重守护**
    --    （该端点**返回**本字段 —— 不返回就读不到最有用的信息、退化成死载荷）。
    detail_json  TEXT,
    source       TEXT                -- 'startup' / 'cli:<script>' / 'api'
);
CREATE INDEX IF NOT EXISTS idx_platform_audit_ts ON platform_audit (id DESC);

-- v0.9.15 d2：`db_dir` 唯一索引 `idx_tenants_db_dir` **刻意不建在这里** ——
--   它由 `tenant_repo._run_platform_migrations()` **单点创建**，且创建前有重值预检。
-- ⚠️ **为什么不在本文件建**（实施期踩到）：`init_platform_db()` 的顺序是
--   `executescript(本文件)` → `_run_platform_migrations()`
--   ⇒ 若这里也建索引，**存量库带重值时会在预检之前就抛裸 `IntegrityError`**，
--     运维拿到的正是那句「UNIQUE constraint failed」而**不知道是哪两行撞了**。
--   ⇒ 一个性质只允许一个创建点；把它放在**有预检的那一侧**。
-- ⚠️ **目标不变量**：`db_dir` 建成后**永不重写**（改 slug 不搬数据）。
--   ⛔ **截至本注释写下时它还没被强制** —— `_MUTABLE_TENANT_FIELDS` 目前**仍含** `db_dir`
--   ⇒ 由 v0.9.15 **d4** 把它移出白名单并配测。**在那之前这只是一句意图，不是守护。**
