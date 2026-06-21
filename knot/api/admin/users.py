"""knot/api/admin/users.py — 用户管理路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.api.schemas import CreateUserRequest, UpdateUserRequest
from knot.repositories import data_source_repo, user_repo
from knot.services import auth_service
from knot.services.engine_cache import invalidate_engine_cache

router = APIRouter()


# ── Users ─────────────────────────────────────────────────────────────

@router.get("/api/admin/users")
async def admin_list_users(admin=Depends(require_admin)):
    users = user_repo.list_users()
    user_sources_map = data_source_repo.get_all_user_source_ids()
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "display_name": u["display_name"] or u["username"],
            "role": u["role"],
            "is_active": u["is_active"],
            "created_at": u["created_at"],
            "source_ids": user_sources_map.get(u["id"], []),
        }
        for u in users
    ]


_VALID_ROLES = {"admin", "analyst"}


@router.post("/api/admin/users")
async def admin_create_user(req: CreateUserRequest, request: Request, admin=Depends(require_admin)):
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="角色必须是 admin 或 analyst")
    ph = auth_service.hash_password(req.password)
    ok = user_repo.create_user(
        req.username, ph, req.display_name or req.username, req.role,
        req.doris_host, req.doris_port, req.doris_user, req.doris_password, req.doris_database,
    )
    if not ok:
        audit(request, admin, action="user.create", resource_type="user",
              success=False, detail={"username": req.username, "error": "duplicate"})
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = user_repo.get_user_by_username(req.username)
    audit(request, admin, action="user.create", resource_type="user",
          resource_id=user["id"], detail={"username": user["username"], "role": req.role})
    return {"id": user["id"], "username": user["username"], "ok": True}


@router.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, req: UpdateUserRequest, request: Request, admin=Depends(require_admin)):
    if req.role is not None and req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="角色必须是 admin 或 analyst")
    kwargs = {k: v for k, v in req.dict().items() if v is not None and k not in ("password", "source_ids")}
    if "default_source_id" in req.__fields_set__:
        kwargs["default_source_id"] = req.default_source_id
    if req.password:
        kwargs["password_hash"] = auth_service.hash_password(req.password)
    # v0.4.5 R-39：敏感字段 PATCH 空值/mask 占位 → 保留原值（不清空）
    if "doris_password" in kwargs:
        from knot.api._secret import should_update_secret
        existing = user_repo.get_user_by_id(user_id) or {}
        should, _ = should_update_secret(kwargs["doris_password"], existing.get("doris_password") or "")
        if not should:
            kwargs.pop("doris_password")
    if kwargs:
        user_repo.update_user(user_id, **kwargs)
    if "source_ids" in req.__fields_set__:
        data_source_repo.set_user_sources(user_id, req.source_ids or [])
    invalidate_engine_cache(user_id)
    # 区分子动作：role_change / password_reset / generic update
    fields_set = set(req.__fields_set__)
    if "role" in fields_set and req.role is not None:
        audit(request, admin, action="user.role_change", resource_type="user",
              resource_id=user_id, detail={"new_role": req.role})
    elif "password" in fields_set and req.password:
        audit(request, admin, action="user.password_reset", resource_type="user",
              resource_id=user_id)
    else:
        audit(request, admin, action="user.update", resource_type="user",
              resource_id=user_id, detail={"fields": sorted(fields_set)})
    return {"ok": True}


@router.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="无法删除自己的账号")
    user_repo.update_user(user_id, is_active=0)
    audit(request, admin, action="user.disable", resource_type="user", resource_id=user_id)
    return {"ok": True}
