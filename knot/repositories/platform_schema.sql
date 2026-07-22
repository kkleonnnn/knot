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
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);
