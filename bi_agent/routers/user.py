from fastapi import APIRouter, Depends

import config as cfg
import persistence
from ..dependencies import get_current_user
from ..schemas import AgentModelConfigRequest, UpdateUserConfigRequest

router = APIRouter()


@router.get("/api/user/agent-models")
async def get_user_agent_models(user=Depends(get_current_user)):
    config = persistence.get_user_agent_model_config(user["id"])
    global_cfg = persistence.get_agent_model_config()
    return {
        "clarifier":   config.get("clarifier")   or global_cfg.get("clarifier", ""),
        "sql_planner": config.get("sql_planner") or global_cfg.get("sql_planner", ""),
        "presenter":   config.get("presenter")   or global_cfg.get("presenter", ""),
    }


@router.put("/api/user/agent-models")
async def set_user_agent_models(req: AgentModelConfigRequest, user=Depends(get_current_user)):
    persistence.set_user_agent_model_config(user["id"], {
        "clarifier":   req.clarifier,
        "sql_planner": req.sql_planner,
        "presenter":   req.presenter,
    })
    return {"ok": True}


@router.get("/api/user/config")
async def get_user_config(user=Depends(get_current_user)):
    settings_map = {s["model_key"]: s for s in persistence.get_model_settings()}
    usage = persistence.get_user_monthly_usage(user["id"])
    enabled_models = [
        {
            "id": key, "name": m["display"].split(" · ")[0],
            "provider": m["provider"].capitalize(),
            "model_id": key,
            "input_price": m["input_price"], "output_price": m["output_price"],
            "is_default": settings_map.get(key, {}).get("is_default", 1 if key == cfg.DEFAULT_MODEL else 0),
            "enabled": settings_map.get(key, {}).get("enabled", 1),
        }
        for key, m in cfg.MODELS.items()
        if settings_map.get(key, {}).get("enabled", 1)
    ]
    return {
        "api_key":            user.get("api_key") or "",
        "preferred_model":    user.get("preferred_model") or cfg.DEFAULT_MODEL,
        "temperature":        user.get("temperature") if user.get("temperature") is not None else 0.2,
        "max_tokens":         user.get("max_tokens") or 4096,
        "top_p":              user.get("top_p") if user.get("top_p") is not None else 0.95,
        "monthly_tokens":     usage.get("monthly_tokens", 0),
        "monthly_cost_usd":   usage.get("monthly_cost_usd", 0.0),
        "avg_response_ms":    usage.get("avg_response_ms", 0),
        "query_count":        usage.get("query_count", 0),
        "models":             enabled_models,
        # v0.2.1 批次2：API key 归口管理员；用户层永远返回空字符串
        "openrouter_api_key": "",
        "embedding_api_key":  "",
    }


@router.put("/api/user/config")
async def update_user_config(req: UpdateUserConfigRequest, user=Depends(get_current_user)):
    # v0.2.1 批次2：API key 归口管理员，用户写入直接忽略
    blocked = {"openrouter_api_key", "embedding_api_key"}
    kwargs = {k: v for k, v in req.dict().items() if v is not None and k not in blocked}
    if kwargs:
        persistence.update_user(user["id"], **kwargs)
    return {"ok": True}
