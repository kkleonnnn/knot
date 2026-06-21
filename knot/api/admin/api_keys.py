"""knot/api/admin/api_keys.py — 应用级 API Key 管理路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.repositories import settings_repo

router = APIRouter()


# ── API Keys (app-level, admin-only) ───────────────────────────────────

@router.get("/api/admin/api-keys")
async def get_api_keys(admin=Depends(require_admin)):
    """v0.4.5 R-39：返回 masked 形式（••••••••last4），不漏明文。"""
    from knot.api._secret import mask_secret
    return {
        "openrouter_api_key": mask_secret(settings_repo.get_app_setting("openrouter_api_key", "")),
        "embedding_api_key":  mask_secret(settings_repo.get_app_setting("embedding_api_key", "")),
    }


@router.put("/api/admin/api-keys")
async def set_api_keys(payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """v0.4.5 R-39：PATCH 空字符串 / mask 占位 → 保留原值；新明文 → 加密更新。
    v0.4.6：变更入审计（detail 不含明文也不含密文，只记 action 类型 + 字段名）。
    """
    from knot.api._secret import should_update_secret
    changed: list[str] = []
    cleared: list[str] = []
    for key in ("openrouter_api_key", "embedding_api_key"):
        if key in payload:
            old = settings_repo.get_app_setting(key, "")
            should, final = should_update_secret(payload[key], old)
            if should:
                settings_repo.set_app_setting(key, final)
                if final:
                    changed.append(key)
                else:
                    cleared.append(key)
    if changed:
        audit(request, admin, action="api_key.set_global", resource_type="api_key",
              detail={"keys": changed})
    if cleared:
        audit(request, admin, action="api_key.clear_global", resource_type="api_key",
              detail={"keys": cleared})
    return {"ok": True}
