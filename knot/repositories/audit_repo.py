"""audit_repo — audit_log 表 CRUD（v0.4.6）。

R-50 INSERT-only 守护：本模块**只暴露** `insert / list_filtered / delete_older_than`；
**严禁** 暴露 update / delete_by_id 等行级 mutation。purge 脚本（commit #5）通过
`delete_older_than(days)` 批量删过期数据，是唯一删除入口。
"""
from __future__ import annotations

import json
from typing import Any

from knot.repositories.base import get_conn


def insert(
    *,
    actor_id: int | None,
    actor_role: str | None,
    actor_name: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    success: int = 1,
    detail_json: dict | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> int:
    """单行 INSERT；返回 lastrowid。"""
    payload = json.dumps(detail_json or {}, ensure_ascii=False)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO audit_log "
        "(actor_id, actor_role, actor_name, action, resource_type, resource_id, "
        " success, detail_json, client_ip, user_agent, request_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (actor_id, actor_role, actor_name, action, resource_type, resource_id,
         success, payload, client_ip, user_agent, request_id),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def list_filtered(
    *,
    actor_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = 1,
    size: int = 50,
) -> list[dict]:
    """admin GET 路由用；强制分页（R-61：上限由 api 层 cap 至 200）。"""
    page = max(1, page)
    size = max(1, size)
    where: list[str] = []
    params: list[Any] = []
    if actor_id is not None:
        where.append("actor_id=?")
        params.append(actor_id)
    if action:
        where.append("action=?")
        params.append(action)
    if resource_type:
        where.append("resource_type=?")
        params.append(resource_type)
    if since:
        where.append("created_at >= ?")
        params.append(since)
    if until:
        where.append("created_at <= ?")
        params.append(until)
    sql = "SELECT * FROM audit_log"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([size, (page - 1) * size])
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        # detail_json 反序列化（便于上层直接用）
        try:
            d["detail_json"] = json.loads(d["detail_json"]) if d.get("detail_json") else {}
        except Exception:
            pass
        out.append(d)
    return out


def delete_older_than(days: int, dry_run: bool = False) -> int:
    """purge 脚本（commit #5）唯一删除入口；返回受影响行数。"""
    conn = get_conn()
    if dry_run:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log "
            "WHERE created_at < datetime('now','localtime', ?)",
            (f"-{days} days",),
        ).fetchone()
        conn.close()
        return row["n"] if row else 0
    cur = conn.execute(
        "DELETE FROM audit_log "
        "WHERE created_at < datetime('now','localtime', ?)",
        (f"-{days} days",),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
