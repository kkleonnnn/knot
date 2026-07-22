"""bi_report_schedule_repo — v0.8.17 (②c) 报表定时刷新配置 + fire 台账 薄 SQL。

⚠️ OOS-1v2 sustained（租户库内禁列 · 隔离靠 per-tenant 文件边界）：catalog_id 水平切分 ≠ 租户隔离；`_reject_forbidden` 拒 tenant_id/project_id。
镜像 monitor_repo（get_conn / close / dict 返回 / _COLS / _UPDATABLE / MetadataError）。
v1 一报一 schedule（UNIQUE report_id）；fire 台账 append-only。
`claim` = 原子认领（守护者 B-4）：next_run_at recompute 与 WHERE 门在**同一 UPDATE**，rowcount==1 才 fire。
"""
from __future__ import annotations

from knot.models.errors import MetadataError
from knot.repositories.base import get_conn

_COLS = (
    "id, report_id, catalog_id, enabled, cadence, interval_hours, run_at_hhmm, "
    "next_run_at, last_fired_at, created_by, created_at, updated_at"
)
_UPDATABLE = ("enabled", "cadence", "interval_hours", "run_at_hhmm", "next_run_at")
_FORBIDDEN = ("tenant_id", "project_id")
_FIRE_COLS = "id, schedule_id, report_id, status, error, refresh_seq, fired_at"


def _reject_forbidden(fields: dict) -> None:
    bad = [k for k in fields if k in _FORBIDDEN]
    if bad:
        raise MetadataError(f"OOS-1v2（租户库内禁列）：schedule 严禁 {bad}（catalog_id 水平切分非租户隔离）")


def get_by_report(report_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT {_COLS} FROM bi_report_schedules WHERE report_id=?", (report_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_schedule(report_id: int, catalog_id: int = 1, created_by: int | None = None, **fields) -> None:
    """建/改 report 的 schedule（UNIQUE report_id → 有则 update，无则 insert）。next_run_at 由 service 算好传入。"""
    _reject_forbidden(fields)
    cols = [k for k in _UPDATABLE if k in fields]
    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM bi_report_schedules WHERE report_id=?", (report_id,)).fetchone()
        if existing:
            if cols:
                sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now','localtime')"
                conn.execute(f"UPDATE bi_report_schedules SET {sets} WHERE report_id=?",
                             [*[fields[c] for c in cols], report_id])
        else:
            allcols = ["report_id", "catalog_id", "created_by", *cols]
            ph = ", ".join(["?"] * len(allcols))
            conn.execute(f"INSERT INTO bi_report_schedules ({', '.join(allcols)}) VALUES ({ph})",
                         [report_id, catalog_id, created_by, *[fields[c] for c in cols]])
        conn.commit()
    finally:
        conn.close()


def delete_by_report(report_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bi_report_schedules WHERE report_id=?", (report_id,))
        conn.commit()
    finally:
        conn.close()


def list_due(now_str: str) -> list[dict]:
    """到期候选：enabled 且 next_run_at 非空且 <= now（认领由 claim 原子把关，防重叠 tick 双打）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT {_COLS} FROM bi_report_schedules "
            "WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY id",
            (now_str,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def claim(schedule_id: int, now_str: str, new_next_run_at: str | None) -> int:
    """原子认领（守护者 B-4）：仅当 enabled 且 next_run_at<=now 才 SET last_fired_at=now + next_run_at=new，
    **同一 UPDATE**（认领与推进无窗口）。返 rowcount —— 1=认领成功可 fire；0=已被别的 tick 抢/未到期。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE bi_report_schedules "
            "SET last_fired_at=?, next_run_at=?, updated_at=datetime('now','localtime') "
            "WHERE id=? AND enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=?",
            (now_str, new_next_run_at, schedule_id, now_str),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── fire 台账（append-only；可观测 + 去重佐证）────────────────────────────────────
def record_fire(schedule_id: int, report_id: int, status: str,
                error: str = "", refresh_seq: int | None = None) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO bi_report_schedule_fires (schedule_id, report_id, status, error, refresh_seq) "
            "VALUES (?, ?, ?, ?, ?)",
            (schedule_id, report_id, status, error, refresh_seq),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_fires(report_id: int, limit: int = 50) -> list[dict]:
    """report 的 fire 历史（最近优先），供 ScheduleModal 台账 UI。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT {_FIRE_COLS} FROM bi_report_schedule_fires WHERE report_id=? ORDER BY id DESC LIMIT ?",
            (report_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
