"""monitor_repo — semantic_monitors + monitor_trigger_audit CRUD（v0.7.7 C1 — 事件/规则/动作三层）。

⚠️ OOS-1 死线 sustained：catalog_id = 语义层水平切分（per-catalog monitor 命名空间）≠ 租户隔离。
   `_UPDATABLE` 白名单 + `_reject_forbidden` 拒 tenant_id/project_id 注入。
镜像 metric_repo（get_conn / close / MetadataError / `_COLS` / `_UPDATABLE` / dict 返回）。
事件+规则+动作合一单表（D2 MVP）；trigger_audit append-only 留痕（R-SL-75 每 check 一行）。
"""
from __future__ import annotations

from knot.models.errors import MetadataError
from knot.repositories.base import get_conn

_COLS = (
    "id, catalog_id, name, metric_name, comparator, threshold, baseline_period, "
    "time_window, action_type, action_target, enabled, created_at, updated_at"
)
_UPDATABLE = (
    "name", "metric_name", "comparator", "threshold", "baseline_period",
    "time_window", "action_type", "action_target", "enabled",
)
_FORBIDDEN = ("tenant_id", "project_id")
_TRIGGER_COLS = "id, monitor_id, catalog_id, metric_value, hit, status, detail, created_at"


def _reject_forbidden(fields: dict) -> None:
    bad = [k for k in fields if k in _FORBIDDEN]
    if bad:
        raise MetadataError(f"OOS-1 死线：monitor 严禁 {bad}（catalog_id 水平切分非租户隔离）")


def create_monitor(catalog_id: int = 1, **fields) -> int:
    """新建 monitor；name + metric_name + comparator + threshold 必填。per-catalog name 唯一。"""
    _reject_forbidden(fields)
    cols = [k for k in _UPDATABLE if k in fields]
    for req in ("name", "metric_name", "comparator", "threshold"):
        if req not in cols:
            raise MetadataError(f"monitor 须含 {req}")
    conn = get_conn()
    try:
        placeholders = ", ".join(["?"] * (len(cols) + 1))
        vals = [catalog_id, *[fields[k] for k in cols]]
        cur = conn.execute(
            f"INSERT INTO semantic_monitors (catalog_id, {', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_monitors(catalog_id: int | None = None, enabled_only: bool = False) -> list[dict]:
    """monitors（按 id 升序）；catalog_id 给定则仅该 catalog（OOS-1 隔离）；enabled_only → 仅启用。"""
    conn = get_conn()
    try:
        where, params = [], []
        if catalog_id is not None:
            where.append("catalog_id=?")
            params.append(catalog_id)
        if enabled_only:
            where.append("enabled=1")
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(f"SELECT {_COLS} FROM semantic_monitors{wsql} ORDER BY id", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_monitor(monitor_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT {_COLS} FROM semantic_monitors WHERE id=?", (monitor_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_monitor(monitor_id: int, **fields) -> None:
    _reject_forbidden(fields)
    cols = [k for k in _UPDATABLE if k in fields]
    if not cols:
        return
    conn = get_conn()
    try:
        sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now','localtime')"
        conn.execute(f"UPDATE semantic_monitors SET {sets} WHERE id=?", [*[fields[c] for c in cols], monitor_id])
        conn.commit()
    finally:
        conn.close()


def delete_monitor(monitor_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM semantic_monitors WHERE id=?", (monitor_id,))
        conn.commit()
    finally:
        conn.close()


# ── 触发留痕侧表（append-only R-SL-75：每 check 命中/未命中/skip 一行）──────────────
def create_trigger(monitor_id: int, catalog_id: int = 1, metric_value: float | None = None,
                    hit: int = 0, status: str = "", detail: str = "") -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO monitor_trigger_audit "
            "(monitor_id, catalog_id, metric_value, hit, status, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (monitor_id, catalog_id, metric_value, hit, status, detail),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_triggers(monitor_id: int | None = None, limit: int = 100) -> list[dict]:
    """触发历史（按 id 降序，最近优先）；monitor_id 给定则仅该 monitor。"""
    conn = get_conn()
    try:
        if monitor_id is None:
            rows = conn.execute(
                f"SELECT {_TRIGGER_COLS} FROM monitor_trigger_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_TRIGGER_COLS} FROM monitor_trigger_audit WHERE monitor_id=? ORDER BY id DESC LIMIT ?",
                (monitor_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
