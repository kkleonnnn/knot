"""few_shot_repo — few_shots 表 CRUD。"""
from __future__ import annotations

from bi_agent.repositories.base import get_conn


def list_few_shots(only_active: bool = False) -> list:
    conn = get_conn()
    if only_active:
        rows = conn.execute(
            "SELECT * FROM few_shots WHERE is_active=1 ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM few_shots ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_few_shot(question: str, sql: str, type_: str = "", is_active: int = 1) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO few_shots (question, sql, type, is_active) VALUES (?,?,?,?)",
        (question, sql, type_ or "", 1 if is_active else 0),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_few_shot(fid: int, **kwargs):
    if not kwargs:
        return
    allowed = {"question", "sql", "type", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields) + ", updated_at=datetime('now','localtime')"
    values = list(fields.values()) + [fid]
    conn = get_conn()
    conn.execute(f"UPDATE few_shots SET {set_clause} WHERE id=?", values)
    conn.commit()
    conn.close()


def delete_few_shot(fid: int):
    conn = get_conn()
    conn.execute("DELETE FROM few_shots WHERE id=?", (fid,))
    conn.commit()
    conn.close()


def bulk_insert_few_shots(items: list) -> int:
    """items: list of {question, sql, type?, is_active?}; returns inserted count."""
    if not items:
        return 0
    conn = get_conn()
    conn.executemany(
        "INSERT INTO few_shots (question, sql, type, is_active) VALUES (?,?,?,?)",
        [
            (it.get("question", ""), it.get("sql", ""),
             it.get("type", "") or "", 1 if it.get("is_active", 1) else 0)
            for it in items if it.get("question") and it.get("sql")
        ],
    )
    conn.commit()
    conn.close()
    return len(items)
