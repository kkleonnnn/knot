import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from bi_agent import config as cfg
from bi_agent.adapters.db import doris as db_connector
from bi_agent.api.deps import require_admin
from bi_agent.api.schemas import (
    AgentModelConfigRequest,
    CreateUserRequest,
    DataSourceRequest,
    UpdateDataSourceRequest,
    UpdateUserRequest,
)
from bi_agent.repositories import budget_repo, data_source_repo, settings_repo, user_repo
from bi_agent.services import auth_service, budget_service, cost_service
from bi_agent.services.engine_cache import invalidate_engine_cache

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
async def admin_create_user(req: CreateUserRequest, admin=Depends(require_admin)):
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="角色必须是 admin 或 analyst")
    ph = auth_service.hash_password(req.password)
    ok = user_repo.create_user(
        req.username, ph, req.display_name or req.username, req.role,
        req.doris_host, req.doris_port, req.doris_user, req.doris_password, req.doris_database,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = user_repo.get_user_by_username(req.username)
    return {"id": user["id"], "username": user["username"], "ok": True}


@router.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, req: UpdateUserRequest, admin=Depends(require_admin)):
    if req.role is not None and req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="角色必须是 admin 或 analyst")
    kwargs = {k: v for k, v in req.dict().items() if v is not None and k not in ("password", "source_ids")}
    if "default_source_id" in req.__fields_set__:
        kwargs["default_source_id"] = req.default_source_id
    if req.password:
        kwargs["password_hash"] = auth_service.hash_password(req.password)
    if kwargs:
        user_repo.update_user(user_id, **kwargs)
    if "source_ids" in req.__fields_set__:
        data_source_repo.set_user_sources(user_id, req.source_ids or [])
    invalidate_engine_cache(user_id)
    return {"ok": True}


@router.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="无法删除自己的账号")
    user_repo.update_user(user_id, is_active=0)
    return {"ok": True}


# ── Data Sources ──────────────────────────────────────────────────────

@router.get("/api/admin/datasources")
async def admin_list_datasources(admin=Depends(require_admin)):
    sources = data_source_repo.list_datasources()

    def _test_source(s):
        try:
            engine = db_connector.create_engine(
                s["db_host"], s["db_port"], s["db_user"], s["db_password"], s["db_database"]
            )
            ok, _ = db_connector.test_connection(engine)
            return "online" if ok else "error"
        except Exception:
            return "error"

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        statuses = await asyncio.gather(
            *[loop.run_in_executor(pool, _test_source, s) for s in sources]
        )

    return [
        {
            "id": s["id"], "name": s["name"],
            "description": s.get("description", ""),
            "db_type": s.get("db_type", "doris"),
            "db_host": s["db_host"], "db_port": s["db_port"],
            "db_database": s["db_database"],
            "is_active": s["is_active"], "created_at": s["created_at"],
            "status": status,
        }
        for s, status in zip(sources, statuses)
    ]


@router.post("/api/admin/datasources")
async def admin_create_datasource(req: DataSourceRequest, admin=Depends(require_admin)):
    sid = data_source_repo.create_datasource(
        user_id=admin["id"], name=req.name, description=req.description,
        db_host=req.db_host, db_port=req.db_port, db_user=req.db_user,
        db_password=req.db_password, db_database=req.db_database, db_type=req.db_type,
    )
    return {"id": sid, "ok": True}


@router.put("/api/admin/datasources/{source_id}")
async def admin_update_datasource(source_id: int, req: UpdateDataSourceRequest, admin=Depends(require_admin)):
    kwargs = {k: v for k, v in req.dict().items() if v is not None}
    if kwargs:
        data_source_repo.update_datasource(source_id, **kwargs)
    return {"ok": True}


@router.delete("/api/admin/datasources/{source_id}")
async def admin_delete_datasource(source_id: int, admin=Depends(require_admin)):
    data_source_repo.delete_datasource(source_id)
    return {"ok": True}


# ── Models ────────────────────────────────────────────────────────────

@router.get("/api/admin/models")
async def admin_list_models(admin=Depends(require_admin)):
    settings_map = {s["model_key"]: s for s in settings_repo.get_model_settings()}
    return [
        {
            "id": key, "model_id": key,
            "name": m["display"], "provider": m["provider"].capitalize(),
            "enabled": settings_map.get(key, {}).get("enabled", 1),
            "is_default": settings_map.get(key, {}).get("is_default", 1 if key == cfg.DEFAULT_MODEL else 0),
            "input_price": m["input_price"], "output_price": m["output_price"],
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
async def set_agent_model_config(req: AgentModelConfigRequest, admin=Depends(require_admin)):
    settings_repo.set_agent_model_config({
        "clarifier":   req.clarifier,
        "sql_planner": req.sql_planner,
        "presenter":   req.presenter,
    })
    return {"ok": True}


# ── Cost Stats (v0.4.2 admin 看板) ─────────────────────────────────────

@router.get("/api/admin/cost-stats")
async def admin_cost_stats(period: str = "7d", admin=Depends(require_admin)):
    """v0.4.2 成本归因汇总（按 agent_kind 分桶 + 按 user 分组）。

    Query params:
      - period: 时段 ('7d' / '30d' / '90d' 或裸数字天)，默认 7d

    返回（详见 message_repo.get_cost_breakdown）：
      {period_days, total_cost_usd, total_messages,
       by_agent_kind: {clarifier, sql_planner, fix_sql, presenter, legacy},
       by_user: [...], recovery_attempt_total}
    """
    return cost_service.get_cost_breakdown_by_period(period)


# ── API Keys (app-level, admin-only) ───────────────────────────────────

@router.get("/api/admin/api-keys")
async def get_api_keys(admin=Depends(require_admin)):
    return {
        "openrouter_api_key": settings_repo.get_app_setting("openrouter_api_key", ""),
        "embedding_api_key":  settings_repo.get_app_setting("embedding_api_key", ""),
    }


@router.put("/api/admin/api-keys")
async def set_api_keys(payload: dict = Body(...), admin=Depends(require_admin)):
    if "openrouter_api_key" in payload:
        settings_repo.set_app_setting("openrouter_api_key", payload["openrouter_api_key"] or "")
    if "embedding_api_key" in payload:
        settings_repo.set_app_setting("embedding_api_key", payload["embedding_api_key"] or "")
    return {"ok": True}


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/api/admin/stats")
async def admin_stats(admin=Depends(require_admin)):
    users = user_repo.list_users()
    sources = data_source_repo.list_datasources()
    return {
        "total_users":     len(users),
        "total_admins":    sum(1 for u in users if u["role"] == "admin"),
        "total_sources":   len(sources),
        "monthly_cost_usd": user_repo.get_monthly_cost(),
    }


# ── Budgets (v0.4.3 R-18/R-21) ─────────────────────────────────────────

class BudgetUpsertRequest(BaseModel):
    scope_type: str       # 'user' | 'agent_kind' | 'global'
    scope_value: str      # user_id (str) | agent_kind | 'all'
    budget_type: str      # 'monthly_cost_usd' | 'monthly_tokens' | 'per_call_cost_usd'
    threshold: float
    action: str = "warn"  # 'warn' | 'block'（block 仅 agent_kind/per_call）
    enabled: int = 1


class BudgetUpdateRequest(BaseModel):
    threshold: Optional[float] = None
    action: Optional[str] = None
    enabled: Optional[int] = None


@router.get("/api/admin/budgets")
async def admin_list_budgets(admin=Depends(require_admin)):
    return budget_repo.list_all()


@router.post("/api/admin/budgets")
async def admin_upsert_budget(req: BudgetUpsertRequest, admin=Depends(require_admin)):
    """v0.4.3 R-18 幂等：UNIQUE 冲突时 INSERT OR REPLACE 覆盖；返 already_existed flag。
    R-21 守护：拒 (agent_kind, legacy) + 'block' 范围限制。"""
    err = budget_service.validate_budget_input(
        req.scope_type, req.scope_value, req.budget_type, req.action,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    existing = budget_repo.get_by_unique(req.scope_type, req.scope_value, req.budget_type)
    rid = budget_repo.upsert(
        req.scope_type, req.scope_value, req.budget_type,
        req.threshold, req.action, req.enabled,
    )
    saved = budget_repo.get(rid) or {}
    return {**saved, "already_existed": existing is not None}


@router.put("/api/admin/budgets/{budget_id}")
async def admin_update_budget(budget_id: int, req: BudgetUpdateRequest, admin=Depends(require_admin)):
    if budget_repo.get(budget_id) is None:
        raise HTTPException(status_code=404, detail="预算不存在")
    # action 改动需重跑校验（避免改成 block + 错配 scope）
    if req.action is not None:
        existing = budget_repo.get(budget_id)
        err = budget_service.validate_budget_input(
            existing["scope_type"], existing["scope_value"],
            existing["budget_type"], req.action,
        )
        if err:
            raise HTTPException(status_code=400, detail=err)
    budget_repo.update(budget_id, threshold=req.threshold, action=req.action, enabled=req.enabled)
    return budget_repo.get(budget_id)


@router.delete("/api/admin/budgets/{budget_id}")
async def admin_delete_budget(budget_id: int, admin=Depends(require_admin)):
    if budget_repo.get(budget_id) is None:
        raise HTTPException(status_code=404, detail="预算不存在")
    budget_repo.delete(budget_id)
    return {"ok": True}


# ── System Recovery 趋势（v0.4.3 R-19）──────────────────────────────────

@router.get("/api/admin/recovery-stats")
async def admin_recovery_stats(period: str = "30d", admin=Depends(require_admin)):
    """v0.4.3 自纠正趋势（R-19 过滤 legacy + v0.4.2 上线日起点）。

    Query params:
      - period: '7d' / '30d' / '90d' 或裸数字天，默认 30d

    返回（详见 message_repo.get_recovery_trend）：
      {period_days, total_recovery_attempts, total_messages,
       by_day: [{date, count, msg_count}, ...],
       top_users: [{user_id, username, count, msg_count}, ...]}
    """
    days = 30
    s = (period or "").strip().lower()
    if s.endswith("d") and s[:-1].isdigit():
        days = max(1, int(s[:-1]))
    elif s.isdigit():
        days = max(1, int(s))
    return budget_service.get_recovery_trend(period_days=days)
