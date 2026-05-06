from __future__ import annotations

"""upload_repo — file_uploads 表（用户上传 CSV/Excel 元数据）。"""
import json

from bi_agent.repositories.base import get_conn


def create_file_upload(user_id: int, filename: str, table_name: str,
                       row_count: int, columns: list) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO file_uploads (user_id, filename, table_name, row_count, columns_json) "
        "VALUES (?,?,?,?,?)",
        (user_id, filename, table_name, row_count, json.dumps(columns, ensure_ascii=False)),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def list_file_uploads(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM file_uploads WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["columns"] = json.loads(d.get("columns_json") or "[]")
        result.append(d)
    return result


def get_file_upload(upload_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM file_uploads WHERE id=?", (upload_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["columns"] = json.loads(d.get("columns_json") or "[]")
    return d


def delete_file_upload(upload_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM file_uploads WHERE id=?", (upload_id,))
    conn.commit()
    conn.close()
