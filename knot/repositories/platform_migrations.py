"""knot.repositories.platform_migrations — 平台库(platform.db) schema + additive 迁移。

**为什么单独一个文件（v0.9.15）**：`tenant_repo.py` 撞 R-94 size gate（>300）,
而 provisioning 片还要往里加写口 / 起源租户保护 ⇒ 提 ACK 只会很快再撞。
**先例完全同形**：v0.8.22 把 `base.py` 的历史迁移块拆入 `repositories/migrations.py`，
理由原文「base.py 顶死 size-gate，v0.9.0 前置」。本文件对平台库做同一件事。

**关注点边界**：本文件只管「**库的形状**」（schema 文本 + additive 迁移 + 幂等 init）；
「**行的内容**」（tenants CRUD / 解析器 / seed）仍在 `tenant_repo.py`。
⚠️ 连接获取（`get_platform_conn`）**刻意留在** `tenant_repo`：它是全仓 ctx-free 入口、
被 15+ 处引用，搬它会产生一次与本次拆分无关的大范围改动。

⚠️ **`tenant_repo` re-export 本模块的 `init_platform_db`** ⇒ 既有
`tenant_repo.init_platform_db()` 调用点（生产 + 测共 10+ 处）**byte-equal 不变**
（照 `base.py` re-export `migrations._migrate_uploads_*` 的既有做法）。
"""

from __future__ import annotations

from pathlib import Path

_PLATFORM_SCHEMA = (Path(__file__).parent / "platform_schema.sql").read_text(encoding="utf-8")


def run_platform_migrations(conn) -> None:
    """平台库 additive 迁移（**本仓第一条** —— v0.9.7）。

    ⚠️ **为什么必须有这个函数**：`platform_schema.sql` 只有 `CREATE TABLE IF NOT EXISTS`
    ⇒ 对**已存在**的 `platform.db`，往 schema 里加列是**完全无效**的（executescript 直接 no-op）。
    此前平台库从未加过列，故一直没暴露；v0.9.7 是第一次。
    范式照租户库 `repositories/migrations.py`（18 处先例）：幂等 `PRAGMA table_info` → `ALTER TABLE ADD COLUMN`。
    """
    # v0.9.7 B-3 ③: tenants.allowed_http_hosts —— per-tenant egress allowlist（部署方控制）。
    # 新库由 platform_schema.sql 的 CREATE 直接带上；本 ALTER 兜住存量库。三态语义见该文件注释。
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    if "allowed_http_hosts" not in cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN allowed_http_hosts TEXT")

    # v0.9.18 P-a: tenants.allowed_webhook_hosts —— webhook 外发 allowlist（与上一列同三态、不同能力）。
    # ⭐ **本条是本机制的第三个用户** ⇒ 「加平台列」已是可组合的常规动作（v0.9.7 第一 · v0.9.8 第二）。
    # ⚠️ 存量库升上来时该列为 NULL ⇒ 起源租户回退 env、非起源租户全拒（fail-closed），
    #    **与本列不存在时的行为一致** ⇒ 迁移本身不改变任何现网行为。
    if "allowed_webhook_hosts" not in cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN allowed_webhook_hosts TEXT")

    # v0.9.8: tenants.updated_at —— 平台元数据变更时间线（此前缺 ⇒「谁改了 db_dir」无时间线）。
    # ⭐ **本条是本机制的第二个用户** —— 它顺带证明「加平台列」不是一次性动作而是可组合的：
    #   从**既无 allowed_http_hosts 也无 updated_at** 的 pre-v0.9.7 存量库升级，一次调用后两列都在
    #   （守护者 M4：只从 pre-v0.9.8 起测只能证明「第二条能跑」，证明不了「两条能串起来」）。
    # 逐块重读列集 —— 照 `migrations.py` 的既有惯用（同一张表 `users` 在 :57/:121/:148 读了三次）。
    # ⚠️ **理由是「块间独立」，不是「否则会坏」**（实施期取材证伪了我原先写的诊断）：
    #   对 additive-only 且检查**不同**列的迁移，顶部取一次快照**永远足够** ——
    #   陈旧快照缺的正是要加的列，条件照样成立。重读的价值在于每块自包含
    #   ⇒ 将来插入/重排迁移块时不必回溯前面改了什么。**别据此写「不重读就会坏」的测。**
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE tenants ADD COLUMN updated_at TEXT")

    # v0.9.15 d2: tenants.db_dir 唯一索引 —— 两个租户指向同一目录 = OOS-1v2 文件边界形同虚设
    #   （主库会被**共用**；实测不对称：uploads 侧会 raise 而主库不会）。
    # ⚠️ **为什么是 INDEX 而不是列上的 UNIQUE 约束**：SQLite 的 `ALTER TABLE` **不能加约束**
    #   ⇒ 对存量库唯一可行的等价物就是 `CREATE UNIQUE INDEX`。
    #   顺带：索引是 `type='index'`，**不进** `test_iso4` 的表集合断言（那条断 `type='table'`）。
    # ⭐ **本条是本机制的第三个用户，也是第一个「非加列」的** ⇒ 它证明这个函数是
    #   「平台库 additive 迁移」而不仅是「加列」。
    # ⭐⭐ **这里是该索引的唯一创建点** —— `platform_schema.sql` **刻意不建**它。
    #   实施期踩到：`init_platform_db()` 先 `executescript(schema)` 再跑本函数
    #   ⇒ 若 schema 里也建，存量库带重值时会在预检**之前**抛裸 `IntegrityError`
    #     （「UNIQUE constraint failed」，不说是哪两行），而本迁移跑在**启动路径**上
    #     ⇒ 预检形同不存在。**一个性质只允许一个创建点；放在有预检的那一侧。**
    _assert_no_duplicate_db_dir(conn)   # ← 必须严格早于下面那行
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_db_dir ON tenants(db_dir)")


def _assert_no_duplicate_db_dir(conn) -> None:
    """建唯一索引**之前**的存量预检：有重值就**点名**是哪些行，而不是让 SQLite 抛裸异常。

    ⚠️ **为什么值得单独一个函数**：`CREATE UNIQUE INDEX` 在有重值时只会给
    `sqlite3.IntegrityError: UNIQUE constraint failed: tenants.db_dir` ——
    **不告诉你是哪两行**。而这条迁移跑在**启动路径**上 ⇒ 运维拿到的就是那句话。
    ⇒ 预检把「哪些 id / slug 撞在哪个 db_dir 上」写进消息，并给出可操作的下一步。
    """
    rows = conn.execute(
        "SELECT db_dir, COUNT(*) AS n, GROUP_CONCAT(id || ':' || slug, ', ') AS who "
        "FROM tenants GROUP BY db_dir HAVING n > 1 ORDER BY db_dir"
    ).fetchall()
    if rows:
        detail = "; ".join(f"db_dir={r[0]!r} 被 {r[1]} 个租户共用（{r[2]}）" for r in rows)
        raise RuntimeError(
            f"[v0.9.15 d2] platform.db 存量数据里 db_dir 有重复，无法建唯一索引：{detail}\n"
            "  ⇒ 两个租户指向同一目录 = OOS-1v2 文件边界形同虚设（主库会被共用）。\n"
            "  ⇒ 处置：确认哪一个是真正在用的租户，把另一个改到自己的目录或停用后清理，再重启。"
        )


def init_platform_db(conn_factory) -> None:
    """建 platform.db + executescript(platform schema) + additive 迁移（幂等 · IF NOT EXISTS）。

    `conn_factory` 由 `tenant_repo` 注入（= `get_platform_conn`）—— 连接获取留在那边，
    本模块只负责「拿到连接之后把库的形状弄对」。
    """
    conn = conn_factory()
    conn.executescript(_PLATFORM_SCHEMA)
    run_platform_migrations(conn)      # v0.9.7：executescript 后 —— 存量库加列的唯一途径
    conn.commit()
    conn.close()
