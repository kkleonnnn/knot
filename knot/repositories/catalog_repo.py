"""catalog_repo — catalogs 表 CRUD + per-user active catalog 解析（v0.6.2.5 段 4 A1）。

⚠️ OOS-1 死线（R-PB-A1-1 守护者强化）：本仓 0 tenant_id/project_id 逻辑 —
   catalog_id = 语义层水平切分（per-user active catalog）≠ 租户数据隔离。
   数据库连接共享（engine_cache key 不动）→ 非多租户隔离架构。

per-user active：每用户 active catalog 由 users.active_catalog_id 解析（NULL → 兜底 catalog id=1）。
本仓只读写 catalogs 表 + users.active_catalog_id；catalog 内容 4 字段（tables/lexicon/
business_rules/relations）形状与 app_settings 4-key byte-equal（R-PB-A1-7）。
"""
from __future__ import annotations

from knot.models.errors import MetadataError
from knot.repositories.base import get_conn

# catalogs 表读取列（与 schema.sql 一致；0 tenant_id — OOS-1 死线）
_COLS = "id, name, description, tables, lexicon, business_rules, relations, field_labels, created_at, updated_at"

# update 仅允许 7 个内容/元字段（v0.7.27 +field_labels；不允许改 id / created_at / 注入 tenant_id）
_UPDATABLE = ("name", "description", "tables", "lexicon", "business_rules", "relations", "field_labels")


def list_catalogs() -> list[dict]:
    """所有 catalog（按 id 升序）。"""
    conn = get_conn()
    try:
        rows = conn.execute(f"SELECT {_COLS} FROM catalogs ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_catalog(catalog_id: int) -> dict | None:
    """单个 catalog；不存在返 None。"""
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT {_COLS} FROM catalogs WHERE id=?", (catalog_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_catalog(
    name: str,
    description: str = "",
    tables: str = "",
    lexicon: str = "",
    business_rules: str = "",
    relations: str = "",
    field_labels: str = "",
) -> int:
    """新建 catalog；返回新 id。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO catalogs (name, description, tables, lexicon, business_rules, relations, field_labels) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description, tables, lexicon, business_rules, relations, field_labels),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_catalog(catalog_id: int, **fields) -> None:
    """更新 catalog（仅 _UPDATABLE 6 字段 + updated_at；忽略其他 key 防注入）。"""
    sets = [(k, v) for k, v in fields.items() if k in _UPDATABLE]
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k, _ in sets)
    vals = [v for _, v in sets]
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE catalogs SET {cols}, updated_at=datetime('now','localtime') WHERE id=?",
            (*vals, catalog_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_catalog(catalog_id: int) -> None:
    """删除 catalog（默认 catalog id=1 不可删的守护在 api 层）。

    删除后仍以 active_catalog_id 指向本行的用户 → get_active_catalog 解析时
    get_catalog 返 None → 兜底 catalog id=1（dangling active 优雅降级，不崩）。
    """
    conn = get_conn()
    try:
        conn.execute("DELETE FROM catalogs WHERE id=?", (catalog_id,))
        conn.commit()
    finally:
        conn.close()


def get_user_active_catalog_id(user_id: int) -> int:
    """per-user active catalog_id；users.active_catalog_id 为 NULL/缺失 → 兜底 catalog id=1。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT active_catalog_id FROM users WHERE id=?", (user_id,)).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 1
    finally:
        conn.close()


def set_user_active_catalog(user_id: int, catalog_id: int) -> None:
    """切换当前用户 active catalog。catalog_id 不存在 → MetadataError（拒绝切到幽灵 catalog）。"""
    conn = get_conn()
    try:
        if not conn.execute("SELECT 1 FROM catalogs WHERE id=?", (catalog_id,)).fetchone():
            raise MetadataError(f"catalog id={catalog_id} 不存在 — 拒绝切换")
        conn.execute("UPDATE users SET active_catalog_id=? WHERE id=?", (catalog_id, user_id))
        conn.commit()
    finally:
        conn.close()


def get_active_catalog(user_id: int) -> dict:
    """解析当前用户 active catalog 行 + 兜底熔断（Stage 2 修订 3 — ε2 fail-fast 精神）。

    解析链：users.active_catalog_id → catalogs 行；缺失 → 兜底 catalog id=1。
    真空期熔断：catalogs 表完全无行（迁移未跑 / 被清空）→ MetadataError 强制中断，
    拒绝静默服务空 catalog（与 v0.6.2.1 ε2 + v0.4.5 R-45 master_key fail-fast 同精神）。
    注：app_settings 4-key legacy 兜底层在 catalog.py reload（commit 3）叠加于本熔断之前。
    """
    cat = get_catalog(get_user_active_catalog_id(user_id))
    if cat is None:
        cat = get_catalog(1)
    if cat is None:
        raise MetadataError(
            "无 active catalog — catalogs 表为空（迁移未执行或被清空）；"
            "拒绝静默服务空 catalog（ε2 fail-fast 精神）",
        )
    return cat
