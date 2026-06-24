"""metric_repo — metrics 表 CRUD（v0.7.0 C1 — 指标注册表地基）。

⚠️ OOS-1 死线 sustained：本仓 0 tenant_id / project_id 逻辑 —
   metric.catalog_id = 语义层水平切分（per-catalog 指标命名空间）≠ 租户数据隔离。
   数据库连接共享 → 非多租户隔离架构。真多租户隔离推 v1.x+。
   `_UPDATABLE` 白名单 + `_reject_forbidden` 入口死锁（拒 tenant_id/project_id 注入）。

镜像 catalog_repo（v0.6.2.5）：get_conn / close / MetadataError / `_COLS` / `_UPDATABLE` / dict 返回。
per-catalog name 唯一（schema `UNIQUE(catalog_id, name)`）。lineage v0.7.16 激活为**结构化派生定义**
`{op,left,right}`（占比/人均 metric÷metric）；repo 仅校验形状（`_validate_lineage`），deps 原子/单层防循环留编译时。
"""
from __future__ import annotations

import json

from knot.models.errors import MetadataError
from knot.repositories.base import get_conn

# metrics 表读取列（与 schema.sql 一致；0 tenant_id — OOS-1 死线）
_COLS = (
    "id, catalog_id, name, display, aliases, caliber, base_object, filters, "
    "dimensions, lineage, freshness_lag_days, enabled, created_at, updated_at"
)

# create / update 允许的内容字段（不含 id / catalog_id / created_at / updated_at；
# 严禁 tenant_id / project_id 注入 — OOS-1 死线）
_UPDATABLE = (
    "name", "display", "aliases", "caliber", "base_object",
    "filters", "dimensions", "lineage", "freshness_lag_days", "enabled",
)

# OOS-1 死线：严禁列（防顺手引租户隔离）
_FORBIDDEN_KEYS = ("tenant_id", "project_id")


def _reject_forbidden(fields: dict) -> None:
    """OOS-1 入口死锁：payload 含 tenant_id/project_id → MetadataError（防多租户漂移）。"""
    bad = [k for k in _FORBIDDEN_KEYS if k in fields]
    if bad:
        raise MetadataError(f"OOS-1 死线：metric 严禁 {bad} 列（catalog_id = 水平切分非租户隔离）")


# v0.7.16 派生指标 op 白名单（与 compile_helpers._OP_SQL 对齐；repo ⊥ semantic 层不 import，本地常量）
_DERIVED_OPS = {"divide", "multiply", "add", "subtract"}


def _validate_lineage(lineage) -> None:
    """派生 metric lineage 校验（v0.7.16）：空（原子）OK；非空须**结构化派生定义** {op∈白名单, left, right}。

    deps 原子性 / 跨注册表存在 / 单层防循环留**编译时**（compiler `_derived_expr`）——repo 仅校验形状。
    """
    if not lineage:
        return  # 原子 metric
    try:
        d = json.loads(lineage) if isinstance(lineage, str) else lineage
    except (ValueError, TypeError):
        raise MetadataError("lineage 须合法 JSON（派生定义 {op,left,right}）")
    if not (isinstance(d, dict) and d.get("op") in _DERIVED_OPS and d.get("left") and d.get("right")):
        raise MetadataError(f"派生 lineage 须 {{op∈{sorted(_DERIVED_OPS)}, left, right}}")


def list_metrics(catalog_id: int | None = None) -> list[dict]:
    """所有 metric（按 id 升序）；catalog_id 给定则仅该 catalog 的指标。"""
    conn = get_conn()
    try:
        if catalog_id is None:
            rows = conn.execute(f"SELECT {_COLS} FROM metrics ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLS} FROM metrics WHERE catalog_id=? ORDER BY id", (catalog_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_metric(metric_id: int) -> dict | None:
    """单个 metric；不存在返 None。"""
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT {_COLS} FROM metrics WHERE id=?", (metric_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_metric(catalog_id: int = 1, **fields) -> int:
    """新建 metric；返回新 id。name 必填 + (caliber 原子口径 OR lineage 派生定义) 二选一；OOS-1 拒 tenant_id/project_id。

    派生 metric（lineage）免 caliber → 插 '' 满足 schema NOT NULL（0 schema 改）。
    per-catalog name 重复 → sqlite3.IntegrityError（schema UNIQUE(catalog_id, name)）。
    """
    _reject_forbidden(fields)
    cols = [k for k in _UPDATABLE if k in fields]
    _validate_lineage(fields.get("lineage"))   # v0.7.16 派生定义形状校验
    if "name" not in cols:
        raise MetadataError("metric 须含 name")
    if "caliber" not in cols and not fields.get("lineage"):   # 原子须 caliber；派生（lineage）免 caliber
        raise MetadataError("metric 须含 caliber（原子口径）或 lineage（派生定义 {op,left,right}）")
    if "caliber" not in fields:               # 派生免 caliber → 插 '' 满足 schema NOT NULL（R-SL-132 0 schema 改）
        fields["caliber"] = ""
        cols = [k for k in _UPDATABLE if k in fields]   # 重算含 caliber
    conn = get_conn()
    try:
        placeholders = ", ".join(["?"] * (len(cols) + 1))
        vals = [catalog_id, *[fields[k] for k in cols]]
        cur = conn.execute(
            f"INSERT INTO metrics (catalog_id, {', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_metric(metric_id: int, **fields) -> None:
    """更新 metric 内容字段（`_UPDATABLE` 白名单；OOS-1 拒 tenant_id/project_id）。无白名单字段 → no-op。"""
    _reject_forbidden(fields)
    cols = [k for k in fields if k in _UPDATABLE]
    if not cols:
        return
    sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now','localtime')"
    vals = [fields[c] for c in cols]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE metrics SET {sets} WHERE id=?", (*vals, metric_id))
        conn.commit()
    finally:
        conn.close()


def delete_metric(metric_id: int) -> None:
    """删除 metric。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM metrics WHERE id=?", (metric_id,))
        conn.commit()
    finally:
        conn.close()
