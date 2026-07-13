"""bi_permission_repo — v0.8.12 BI 目录/报表权限 RBAC 薄 SQL helper。

kk 验收返工：**按用户授权**（user_id，非 role）—— 同角色不同部门可见不同表。
grant 目标二选一：folder_id（目录级，归档报表继承）或 report_id（报表级，未分组逐张）。
admin 不入表（service 层 bypass）。全 4 权限为 0 → 删行（无授权即无行 = 默认拒）。
"""
from __future__ import annotations

from knot.repositories.base import get_conn

_PERMS = ("can_schedule", "can_edit", "can_export", "can_share")


def list_all() -> list[dict]:
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM bi_permissions ORDER BY id").fetchall()]
    finally:
        conn.close()


def get_folder_grant(user_id: int, folder_id: int) -> dict | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM bi_permissions WHERE user_id=? AND folder_id=?",
                         (user_id, folder_id)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def get_report_grant(user_id: int, report_id: int) -> dict | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM bi_permissions WHERE user_id=? AND report_id=?",
                         (user_id, report_id)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def set_folder_grant(user_id: int, folder_id: int, perms: dict, created_by: int) -> None:
    _upsert(user_id, "folder_id", folder_id, perms, created_by)


def set_report_grant(user_id: int, report_id: int, perms: dict, created_by: int) -> None:
    _upsert(user_id, "report_id", report_id, perms, created_by)


def _upsert(user_id: int, col: str, target_id: int, perms: dict, created_by: int) -> None:
    vals = tuple(1 if perms.get(p) else 0 for p in _PERMS)
    conn = get_conn()
    try:
        if not any(vals):                       # 全 0 → 删 grant（默认拒，不留空行）
            conn.execute(f"DELETE FROM bi_permissions WHERE user_id=? AND {col}=?", (user_id, target_id))
        else:
            existing = conn.execute(f"SELECT id FROM bi_permissions WHERE user_id=? AND {col}=?",
                                    (user_id, target_id)).fetchone()
            if existing:
                conn.execute("UPDATE bi_permissions SET can_schedule=?,can_edit=?,can_export=?,can_share=? "
                             "WHERE id=?", (*vals, existing["id"]))
            else:
                other = "report_id" if col == "folder_id" else "folder_id"
                conn.execute(
                    f"INSERT INTO bi_permissions (user_id,{col},{other},"
                    "can_schedule,can_edit,can_export,can_share,created_by) VALUES (?,?,NULL,?,?,?,?,?)",
                    (user_id, target_id, *vals, created_by),
                )
        conn.commit()
    finally:
        conn.close()


def delete_for_folder(folder_id: int) -> None:
    """目录删除级联清其 grant（service delete_folder 调用）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bi_permissions WHERE folder_id=?", (folder_id,))
        conn.commit()
    finally:
        conn.close()


def delete_for_report(report_id: int) -> None:
    """报表删除级联清其 grant（service delete_report 调用）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bi_permissions WHERE report_id=?", (report_id,))
        conn.commit()
    finally:
        conn.close()


def delete_for_user(user_id: int) -> None:
    """用户删除级联清其 grant（防孤儿）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM bi_permissions WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()
