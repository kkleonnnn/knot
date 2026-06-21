"""knot/api/admin/models.py — 模型目录 + Agent 模型配置路由（admin.py 拆分 v0.6.5.11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knot import config as cfg
from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.api.schemas import AgentModelConfigRequest
from knot.repositories import settings_repo

router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────

@router.get("/api/admin/models")
async def admin_list_models(admin=Depends(require_admin)):
    """v0.6.0.6 F-D：响应增加 max_context 字段（OR entries 有；direct provider 无 → None）。"""
    settings_map = {s["model_key"]: s for s in settings_repo.get_model_settings()}
    return [
        {
            "id": key, "model_id": key,
            "name": m["display"], "provider": m["provider"].capitalize(),
            "enabled": settings_map.get(key, {}).get("enabled", 1),
            "is_default": settings_map.get(key, {}).get("is_default", 1 if key == cfg.DEFAULT_MODEL else 0),
            "input_price": m["input_price"], "output_price": m["output_price"],
            "max_context": m.get("max_context"),  # v0.6.0.6 F-D-1：OR entries 有；direct 为 None
        }
        for key, m in cfg.MODELS.items()
    ]


@router.post("/api/admin/models/{model_key}/default")
async def admin_set_default_model(model_key: str, admin=Depends(require_admin)):
    if model_key not in cfg.MODELS:
        raise HTTPException(status_code=404, detail="模型不存在")
    settings_repo.set_default_model(model_key)
    return {"ok": True}


@router.post("/api/admin/models/{model_key}/toggle")
async def admin_toggle_model(model_key: str, admin=Depends(require_admin)):
    if model_key not in cfg.MODELS:
        raise HTTPException(status_code=404, detail="模型不存在")
    settings_map = {s["model_key"]: s for s in settings_repo.get_model_settings()}
    current_enabled = settings_map.get(model_key, {}).get("enabled", 1)
    settings_repo.set_model_enabled(model_key, 0 if current_enabled else 1)
    return {"ok": True, "enabled": 0 if current_enabled else 1}


# ── Agent Model Config ────────────────────────────────────────────────

@router.get("/api/admin/agent-models")
async def get_agent_model_config(admin=Depends(require_admin)):
    config = settings_repo.get_agent_model_config()
    return {
        "clarifier":   config.get("clarifier", ""),
        "sql_planner": config.get("sql_planner", ""),
        "presenter":   config.get("presenter", ""),
    }


@router.put("/api/admin/agent-models")
async def set_agent_model_config(req: AgentModelConfigRequest, request: Request, admin=Depends(require_admin)):
    settings_repo.set_agent_model_config({
        "clarifier":   req.clarifier,
        "sql_planner": req.sql_planner,
        "presenter":   req.presenter,
    })
    audit(request, admin, action="config.agent_models_update", resource_type="agent_model",
          detail={"clarifier": req.clarifier, "sql_planner": req.sql_planner, "presenter": req.presenter})
    return {"ok": True}
