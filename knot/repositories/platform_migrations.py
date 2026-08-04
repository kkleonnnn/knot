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
