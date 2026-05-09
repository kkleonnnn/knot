"""saved_report_repo — saved_reports 表 CRUD（v0.4.1）。

只暴露薄 SQL helper；快照 / fallback / 截断逻辑全部由
services/saved_report_service.py 编排。

UNIQUE (user_id, source_message_id) 是 R-12 幂等键：service 层在调用
create() 前先查 get_by_unique()；冲突时 INSERT OR IGNORE 不抛异常，
service 回查既存对象返回。
"""
from __future__ import annotations

from knot.repositories.base import get_conn


def create(
    user_id: int,
    title: str,
    sql_text: str,
    source_message_id: int | None = None,
    data_source_id: int | None = None,
    question: str | None = None,
    intent: str | None = None,
    display_hint: str | None = None,
    pin_note: str | None = None,
    last_run_at: str | None = None,
    last_run_rows_json: str | None = None,
    last_run_truncated: int = 0,
    last_run_ms: int = 0,
) -> int:
    """INSERT OR IGNORE — UNIQUE (user_id, source_message_id) 冲突时不抛。
    返回 lastrowid；如果是冲突跳过则返回 0（service 层据此判断是否回查既存）。
    """
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO saved_reports "
        "(user_id, source_message_id, data_source_id, title, question, sql_text, "
        " intent, display_hint, pin_note, "
        " last_run_at, last_run_rows_json, last_run_truncated, last_run_ms) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, source_message_id, data_source_id, title, question, sql_text,
         intent, display_hint, pin_note,
         last_run_at, last_run_rows_json, last_run_truncated, last_run_ms),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def get(report_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM saved_reports WHERE id=?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_unique(user_id: int, source_message_id: int | None) -> dict | None:
    """R-12 幂等查询：user 已有对该 message 的 pin 时返既存行；否则 None。
    source_message_id=None（手工建报表场景）一律返 None（不做去重）。
    """
    if source_message_id is None:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM saved_reports WHERE user_id=? AND source_message_id=?",
        (user_id, source_message_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_for_user(user_id: int) -> list[dict]:
    """按 pinned_at DESC 排（最近收藏在前）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM saved_reports WHERE user_id=? ORDER BY pinned_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update(report_id: int, title: str | None = None, pin_note: str | None = None) -> None:
    """改 title / pin_note；None 表示不动该字段。"""
    sets: list[str] = []
    params: list = []
    if title is not None:
        sets.append("title=?")
        params.append(title)
    if pin_note is not None:
        sets.append("pin_note=?")
        params.append(pin_note)
    if not sets:
        return
    params.append(report_id)
    conn = get_conn()
    conn.execute(f"UPDATE saved_reports SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()


def update_last_run(
    report_id: int,
    rows_json: str,
    truncated: int,
    elapsed_ms: int,
    run_at: str,
) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE saved_reports SET "
        "last_run_rows_json=?, last_run_truncated=?, last_run_ms=?, last_run_at=? "
        "WHERE id=?",
        (rows_json, truncated, elapsed_ms, run_at, report_id),
    )
    conn.commit()
    conn.close()


def delete(report_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM saved_reports WHERE id=?", (report_id,))
    conn.commit()
    conn.close()
