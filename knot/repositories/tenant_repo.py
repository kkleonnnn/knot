"""knot.repositories.tenant_repo — 平台库(platform.db) 连接 + tenants 表 CRUD + 单租户解析器。

平台库存平台元数据（v0.9.0 仅 tenants 表）；租户库 = `SQLITE_DB_PATH.parent / db_dir / knot.db`
（`base.get_conn` 双层解析）。存量迁移（pre-tenancy knot.db → tenant#1 库）在 `tenancy_migration.py`。

`get_platform_conn` **ctx-free**（不经 fail-closed `get_conn`）—— 供启动序 platform bootstrap +
tenant 解析 + C4 迁移；否则自身撞 fail-closed 门（chicken-and-egg）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from knot.config import SQLITE_DB_PATH
from knot.core.tenant_context import TenantContextError

_PLATFORM_SCHEMA = (Path(__file__).parent / "platform_schema.sql").read_text(encoding="utf-8")

# v0.9.0 生产 tenant#1 库目录（相对 SQLITE_DB_PATH.parent）；存量迁移把 knot.db 迁入此处。
DEFAULT_TENANT_DB_DIR = "tenants/1"


def _platform_db_path() -> Path:
    """平台库路径 = 数据目录锚点(SQLITE_DB_PATH.parent) / platform.db（不引新 env）。"""
    return Path(SQLITE_DB_PATH).parent / "platform.db"


def get_platform_conn() -> sqlite3.Connection:
    """平台库连接（**ctx-free** — 不经 fail-closed get_conn）。"""
    conn = sqlite3.connect(_platform_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_platform_db() -> None:
    """建 platform.db + executescript(platform schema)（幂等 · IF NOT EXISTS）。"""
    conn = get_platform_conn()
    conn.executescript(_PLATFORM_SCHEMA)
    conn.commit()
    conn.close()


def list_tenants() -> list:
    conn = get_platform_conn()
    rows = conn.execute("SELECT * FROM tenants ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_active_tenants() -> list:
    conn = get_platform_conn()
    rows = conn.execute("SELECT * FROM tenants WHERE status='active' ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tenant(tenant_id: int) -> dict | None:
    conn = get_platform_conn()
    row = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_default_tenant(db_dir: str = DEFAULT_TENANT_DB_DIR) -> None:
    """seed 恰 1 行 tenant#1（幂等：tenants 非空则跳）。生产 db_dir='tenants/1'；测试传 '.'。"""
    conn = get_platform_conn()
    if conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO tenants (id, slug, name, status, db_dir) VALUES (1, 'default', '默认租户', 'active', ?)",
            (db_dir,),
        )
        conn.commit()
    conn.close()


def resolve_tenant_by_id(tenant_id: int) -> dict | None:
    """v0.9.4 D6：按 tid 解析**可服务**租户 —— 存在**且** `status=='active'` 才返，否则 `None`。

    为何不改 `get_tenant` 本身：`tests/test_tenant_isolation.py:56` 依赖它能取出 suspended 行来验文件级隔离。
    ⭐ **B-2 承重**：`get_tenant` 不过滤 status（`SELECT * WHERE id=?`）⇒ 若 tenant_resolution 直接用它，
    平台方停用租户后，该租户用户手里 **7 天有效期**（`deps.py:78` `JWT_EXPIRE_HOURS=24*7`）内的 JWT
    **继续正常查询** —— 停用形同虚设。故解析路径必须走本函数。
    返 `None`（而非 raise）让调用方决定语义：受保护 API → 401；不在此处表达 HTTP 语义。
    """
    t = get_tenant(tenant_id)
    if t is None or t.get("status") != "active":
        return None
    return t


def resolve_tenant_by_slug(slug: str) -> dict | None:
    """v0.9.4 D4''：按**公司代号**（`tenants.slug`）解析**可服务**租户 —— 存在且 active 才返，否则 `None`。

    kk 2026-07-27 决策①「每家公司一条专属登录链接」的落点：链接携带 `?c=<slug>`，登录端点据此
    在**建 ctx 之前**（ctx-free，读平台库）定位租户。
    ⭐ **复用已存在的 `tenants.slug`**（`NOT NULL UNIQUE`）带来的最大连带收益：**不需要**新建
    user_directory 表、**不需要**用户名全局唯一 ⇒ 各租户照样可各有 `admin`
    （避开与 seed 逻辑的正面冲突）。

    **精确匹配（大小写敏感）**：`slug` 的 UNIQUE 是大小写敏感的 ⇒ 若这里做大小写不敏感匹配，
    理论上 `abc` 与 `ABC` 两行都可能存在而本函数只能返一行 = **不确定地把用户送进某个租户**。
    链接是系统生成的、不靠人手打 ⇒ 精确匹配代价可忽略，换来「绝不会解析歧义」。
    返 `None` 而非 raise：调用方（登录端点）要把它折进**统一的**「账号或密码错误」，
    否则「代号不存在」与「代号存在但口令错」可区分 = **公司枚举**（kk 决策②）。
    """
    conn = get_platform_conn()
    row = conn.execute(
        "SELECT * FROM tenants WHERE slug=? AND status='active'", (slug,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def assert_no_second_active_tenant_served() -> None:
    """R-T-GATE 请求侧硬门（v0.9.4 D5 —— **首次真实现**）：active 租户 **>1** 即 fail-closed。

    ⭐ **B-1 承重**：LOCKED（`docs/plans/v0.9.0-oos1-ceremony-multitenant-base.md:150`）把本函数指定为硬 CI，
    但**此前全仓无任何实现** —— 真正在挡的只是 `resolve_single_tenant()` 抛错的**副作用**。v0.9.4 把请求
    路径改为「按 JWT tid 解析」后，`len(active)` 这条判定就不在请求路径上了 ⇒ 必须显式补，否则 R-T-GATE
    在请求侧**无声消失**。

    ⭐ **只对 `>1`**（守护者 Stage 3 R3/MF3 裁定，**不是** `!=1`）：
      - 名副其实（"no **second** active"）；
      - `0 active` 交给上层语义：受保护 API 因无可解析租户自然 401，**登录端点得以返回锁定的
        `401 账号或密码错误`**（②统一错误）而不是 500。若此处对 0 也 raise，唯一租户被 suspend 时
        整站含 login 全部 500，与②直接打架。

    **v0.9.5 lift = 删掉本函数的唯一调用点（一行）** —— 语义单点、可 review。
    """
    n = len(list_active_tenants())
    if n > 1:
        raise TenantContextError(
            f"R-T-GATE：检测到 {n} 个 active 租户，隔离栈就绪前不得同时服务多租户 —— 拒绝服务（fail-closed）。"
            "就绪清单见 CLAUDE.md §R-T-GATE（per-tenant file catalog / http_spec 凭据 / egress 域化 / "
            "开通口令 / 鉴权拆分 / audit-on-drift）"
        )


def resolve_single_tenant() -> dict:
    """v0.9.0 单租户解析器：platform.db tenants 恰 1 active → 返之；0 或 >1 → raise（fail-closed）。

    多租户解析（JWT tid → 库）= 0.1。>1 active 由 R-T-GATE `assert_no_second_active_tenant_served` 挡
    （0.9.0~0.2 期间隔离栈未就绪，永远只有 1 个可服务租户）。
    """
    active = list_active_tenants()
    if len(active) != 1:
        raise TenantContextError(
            f"单租户解析器要求恰 1 个 active tenant；实际 {len(active)}"
            "（R-T-GATE：第二租户开通须待隔离栈就绪 — uploads/凭据/egress/catalog/调度器/缓存键/开通口令）"
        )
    return active[0]
