"""knot/api/admin/share.py — v0.8.14 分享 IM 凭据配置 + 投递目标白名单（admin-only）。

凭据（lark_app_secret / telegram_bot_token 机密 → mask GET / should_update PUT，镜像 api_keys.py；
lark_app_id / lark_region 明文直读写）走 app_settings。白名单走 bi_share_targets（chat_id 非机密）。
审计 config.im_share_update（config.* 家族，resource_type=share_target）。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import require_tenant_admin
from knot.repositories import bi_share_target_repo as target_repo
from knot.repositories import settings_repo

router = APIRouter()

_SECRET_KEYS = ("lark_app_secret", "telegram_bot_token")   # mask GET / should_update PUT
_PLAIN_KEYS = ("lark_app_id", "lark_region")               # 明文直读写


# ── IM 凭据配置 ────────────────────────────────────────────────────────
@router.get("/api/admin/share/config")
async def get_share_config(admin=Depends(require_tenant_admin)):
    from knot.api._secret import mask_secret
    out = {k: mask_secret(settings_repo.get_app_setting(k, "")) for k in _SECRET_KEYS}
    out.update({k: settings_repo.get_app_setting(k, "") for k in _PLAIN_KEYS})
    return out


@router.put("/api/admin/share/config")
async def set_share_config(payload: dict = Body(...), request: Request = None, admin=Depends(require_tenant_admin)):
    from knot.api._secret import should_update_secret
    changed: list[str] = []
    for k in _SECRET_KEYS:
        if k in payload:
            old = settings_repo.get_app_setting(k, "")
            should, final = should_update_secret(payload[k], old)
            if should:
                settings_repo.set_app_setting(k, final)
                changed.append(k)
    for k in _PLAIN_KEYS:
        if k in payload:
            settings_repo.set_app_setting(k, str(payload[k] or ""))
            changed.append(k)
    if changed:
        audit(request, admin, action="config.im_share_update", resource_type="share_target",
              detail={"keys": changed})  # detail 只字段名，无凭据 VALUE
    return {"ok": True}


# ── 投递目标白名单 CRUD ─────────────────────────────────────────────────
class ShareTargetRequest(BaseModel):
    name: str
    platform: str            # 'lark' | 'tg'
    chat_id: str
    region: str | None = None
    data_source_id: int | None = None


@router.get("/api/admin/share/targets")
async def list_share_targets(admin=Depends(require_tenant_admin)):
    return target_repo.list_targets()


@router.post("/api/admin/share/targets")
async def create_share_target(req: ShareTargetRequest, request: Request = None, admin=Depends(require_tenant_admin)):
    if req.platform not in target_repo.PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform 须 ∈ {target_repo.PLATFORMS}")
    if req.platform == "lark" and (req.region or "feishu") not in ("feishu", "lark"):
        raise HTTPException(status_code=400, detail="Lark region 须 feishu / lark")
    if not req.name.strip() or not req.chat_id.strip():
        raise HTTPException(status_code=400, detail="name / chat_id 不能为空")
    tid = target_repo.create_target(
        name=req.name.strip(), platform=req.platform, chat_id=req.chat_id.strip(),
        region=(req.region or None), data_source_id=req.data_source_id, created_by=admin["id"],
    )
    audit(request, admin, action="config.im_share_update", resource_type="share_target",
          resource_id=tid, detail={"target_create": tid, "platform": req.platform})
    return {"id": tid}


@router.delete("/api/admin/share/targets/{target_id}")
async def delete_share_target(target_id: int, request: Request = None, admin=Depends(require_tenant_admin)):
    target_repo.delete_target(target_id)
    audit(request, admin, action="config.im_share_update", resource_type="share_target",
          resource_id=target_id, detail={"target_delete": target_id})
    return {"ok": True}
