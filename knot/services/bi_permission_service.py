"""bi_permission_service — v0.8.12 BI 目录/报表权限 RBAC 解析 + admin bypass。

模型（角色×目录 + 未分组逐报表）：
- admin → 恒全权（不查表）。
- 归档报表（folder_id 非空）→ 继承所属目录的角色 grant。
- 未分组报表（folder_id 空）→ 该报表自己的角色 grant。
- 无 grant → 默认拒（除 admin）。
4 动作：schedule（定时）/ edit（增改删+重跑）/ export（导出）/ share（分享）。单租户内 role×资源（OOS-1，无 tenant_id）。
"""
from __future__ import annotations

from knot.repositories import bi_permission_repo as repo

ACTIONS = ("schedule", "edit", "export", "share")
_COL = {a: f"can_{a}" for a in ACTIONS}


def _is_admin(user) -> bool:
    return bool(user) and user.get("role") == "admin"


def effective(user, report: dict) -> dict:
    """返 {schedule, edit, export, share: bool}。admin 全 True；否则按**用户**×目录/报表 grant 解析（默认拒）。"""
    if _is_admin(user):
        return {a: True for a in ACTIONS}
    uid = (user or {}).get("id")
    folder_id = report.get("folder_id")
    grant = (repo.get_folder_grant(uid, folder_id) if folder_id is not None
             else repo.get_report_grant(uid, report["id"]))
    return {a: bool(grant and grant.get(_COL[a])) for a in ACTIONS}


def can(user, report: dict, action: str) -> bool:
    """user 是否可对 report 执行 action。admin 恒 True；未知 action → False；否则查解析。"""
    if _is_admin(user):
        return True
    if action not in ACTIONS:
        return False
    return effective(user, report).get(action, False)


def can_folder(user, folder_id, action: str) -> bool:
    """user 对某目录是否有 action 权限（create_report 归档建报表用）。admin 恒 True；
    未分组（folder_id None）非 admin → False（无 report_id 可授，未分组建报表仅 admin）。"""
    if _is_admin(user):
        return True
    if folder_id is None or action not in ACTIONS:
        return False
    g = repo.get_folder_grant((user or {}).get("id"), folder_id)
    return bool(g and g.get(_COL[action]))
