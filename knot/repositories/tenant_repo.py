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
