"""bi_permission_repo — v0.8.12 BI 目录/报表权限 RBAC 薄 SQL helper。

grant 目标二选一：folder_id（目录级，归档报表继承）或 report_id（报表级，未分组逐张）。
admin 不入表（service 层 bypass）。解析 / admin bypass / 端点强制由 services/bi_permission_service.py 编排
（镜像 bi_report_repo 纪律）。全 4 权限为 0 → 删行（无授权即无行 = 默认拒）。
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


def get_folder_grant(role: str, folder_id: int) -> dict | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM bi_permissions WHERE role=? AND folder_id=?",
                         (role, folder_id)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def get_report_grant(role: str, report_id: int) -> dict | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM bi_permissions WHERE role=? AND report_id=?",
                         (role, report_id)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def set_folder_grant(role: str, folder_id: int, perms: dict, created_by: int) -> None:
    _upsert(role, "folder_id", folder_id, perms, created_by)


def set_report_grant(role: str, report_id: int, perms: dict, created_by: int) -> None:
    _upsert(role, "report_id", report_id, perms, created_by)


def _upsert(role: str, col: str, target_id: int, perms: dict, created_by: int) -> None:
    vals = tuple(1 if perms.get(p) else 0 for p in _PERMS)
    conn = get_conn()
    try:
        if not any(vals):                       # 全 0 → 删 grant（默认拒，不留空行）
            conn.execute(f"DELETE FROM bi_permissions WHERE role=? AND {col}=?", (role, target_id))
        else:
            existing = conn.execute(f"SELECT id FROM bi_permissions WHERE role=? AND {col}=?",
                                    (role, target_id)).fetchone()
            if existing:
                conn.execute("UPDATE bi_permissions SET can_schedule=?,can_edit=?,can_export=?,can_share=? "
                             "WHERE id=?", (*vals, existing["id"]))
            else:
                other = "report_id" if col == "folder_id" else "folder_id"
                conn.execute(
                    f"INSERT INTO bi_permissions (role,{col},{other},"
                    "can_schedule,can_edit,can_export,can_share,created_by) VALUES (?,?,NULL,?,?,?,?,?)",
                    (role, target_id, *vals, created_by),
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
