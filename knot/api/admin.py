import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from knot import config as cfg
from knot.adapters.db import doris as db_connector
from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.api.schemas import (
    AgentModelConfigRequest,
    CreateUserRequest,
    DataSourceRequest,
    UpdateDataSourceRequest,
    UpdateUserRequest,
)
from knot.repositories import budget_repo, data_source_repo, settings_repo, user_repo
from knot.services import auth_service, budget_service, cost_service
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
async def admin_create_datasource(req: DataSourceRequest, request: Request, admin=Depends(require_admin)):
    sid = data_source_repo.create_datasource(
        user_id=admin["id"], name=req.name, description=req.description,
        db_host=req.db_host, db_port=req.db_port, db_user=req.db_user,
        db_password=req.db_password, db_database=req.db_database, db_type=req.db_type,
    )
    audit(request, admin, action="datasource.create", resource_type="datasource",
          resource_id=sid, detail={"name": req.name, "db_host": req.db_host, "db_database": req.db_database})
    return {"id": sid, "ok": True}


@router.put("/api/admin/datasources/{source_id}")
async def admin_update_datasource(source_id: int, req: UpdateDataSourceRequest, request: Request, admin=Depends(require_admin)):
    kwargs = {k: v for k, v in req.dict().items() if v is not None}
    # v0.4.5 R-39：db_password 空/mask 占位 → 保留原值
    if "db_password" in kwargs:
        from knot.api._secret import should_update_secret
        existing = data_source_repo.get_datasource(source_id) or {}
        should, _ = should_update_secret(kwargs["db_password"], existing.get("db_password") or "")
        if not should:
            kwargs.pop("db_password")
    if kwargs:
        data_source_repo.update_datasource(source_id, **kwargs)
    audit(request, admin, action="datasource.update", resource_type="datasource",
          resource_id=source_id, detail={"fields": sorted(kwargs.keys())})
    return {"ok": True}


@router.delete("/api/admin/datasources/{source_id}")
async def admin_delete_datasource(source_id: int, request: Request, admin=Depends(require_admin)):
    data_source_repo.delete_datasource(source_id)
    audit(request, admin, action="datasource.delete", resource_type="datasource",
          resource_id=source_id)
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
async def set_agent_model_config(req: AgentModelConfigRequest, request: Request, admin=Depends(require_admin)):
    settings_repo.set_agent_model_config({
        "clarifier":   req.clarifier,
        "sql_planner": req.sql_planner,
        "presenter":   req.presenter,
    })
    audit(request, admin, action="config.agent_models_update", resource_type="agent_model",
          detail={"clarifier": req.clarifier, "sql_planner": req.sql_planner, "presenter": req.presenter})
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
async def admin_upsert_budget(req: BudgetUpsertRequest, request: Request, admin=Depends(require_admin)):
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
    audit(request, admin,
          action="budget.update" if existing else "budget.create",
          resource_type="budget", resource_id=rid,
          detail={"scope_type": req.scope_type, "scope_value": req.scope_value,
                  "budget_type": req.budget_type, "threshold": req.threshold,
                  "action": req.action, "enabled": req.enabled})
    return {**saved, "already_existed": existing is not None}


@router.put("/api/admin/budgets/{budget_id}")
async def admin_update_budget(budget_id: int, req: BudgetUpdateRequest, request: Request, admin=Depends(require_admin)):
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
    audit(request, admin, action="budget.update", resource_type="budget", resource_id=budget_id,
          detail={"threshold": req.threshold, "action": req.action, "enabled": req.enabled})
    return budget_repo.get(budget_id)


@router.delete("/api/admin/budgets/{budget_id}")
async def admin_delete_budget(budget_id: int, request: Request, admin=Depends(require_admin)):
    if budget_repo.get(budget_id) is None:
        raise HTTPException(status_code=404, detail="预算不存在")
    budget_repo.delete(budget_id)
    audit(request, admin, action="budget.delete", resource_type="budget", resource_id=budget_id)
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


# ─── v0.5.40 后端真数据 stats endpoints ──────────────────────────────────

@router.get("/api/admin/audit-stats")
async def admin_audit_stats(admin=Depends(require_admin)):
    """v0.5.40 — 审计日志聚合 stats（总记录数/今日/失败数/涉及用户）。"""
    from knot.repositories import get_conn
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) AS today,
          SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed,
          COUNT(DISTINCT actor_id) AS distinct_users
        FROM audit_log
        """
    ).fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "today": row[1] or 0,
        "failed": row[2] or 0,
        "distinct_users": row[3] or 0,
    }


@router.get("/api/admin/budgets-stats")
async def admin_budgets_stats(admin=Depends(require_admin)):
    """v0.5.40 — 预算 Hero card 聚合 stats（本月已用 token / 预计花费 / 使用率）。

    本月已用 token: SUM(input_tokens + output_tokens) 当月 messages
    预计花费: SUM(cost_usd) 当月 messages
    使用率: 若有 global monthly_tokens budget 配置 → tokens_used / threshold
    """
    from knot.repositories import get_conn
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens_used,
          COALESCE(SUM(cost_usd), 0) AS cost_usd
        FROM messages
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')
        """
    ).fetchone()
    tokens_used = row[0] or 0
    cost_usd = row[1] or 0.0
    conn.close()
    # v0.5.42 — 使用率 from app_settings budget_monthly_token_cap（demo 单 global config 模式）
    try:
        cap = int(settings_repo.get_app_setting("budget_monthly_token_cap", "500000"))
    except (ValueError, TypeError):
        cap = None
    usage_pct = (tokens_used / cap * 100) if (cap and cap > 0) else None
    return {
        "tokens_used": tokens_used,
        "cost_usd": round(cost_usd, 4),
        "usage_pct": round(usage_pct, 1) if usage_pct is not None else None,
        "cap": cap,
    }


@router.get("/api/admin/datasources-stats")
async def admin_datasources_stats(admin=Depends(require_admin)):
    """v0.5.40 — DataSources Hero card 聚合 stats（总 schema / 总表数 / 上次心跳）。

    总 schema: 已配置 datasources 中 distinct db_database 数（一个 source = 一个 schema）
    总表数: 从 semantic_layer 缓存（每 source 的 schema_json 中 ### 分隔表数 sum）
    上次心跳: 最近一次 datasources 心跳测试 = 最近 created_at 相对时间（近似实现）
    """
    from knot.repositories import get_conn
    conn = get_conn()
    schemas = conn.execute(
        "SELECT COUNT(DISTINCT db_database) FROM data_sources WHERE is_active = 1"
    ).fetchone()[0] or 0
    # 总表数: 从 semantic_layer schema_json 中数 ### 分隔块
    tables_total = 0
    sem_rows = conn.execute("SELECT schema_text FROM semantic_layer").fetchall()
    for r in sem_rows:
        s = r[0] or ""
        # 每个 ### 标记一张表（与 db/status endpoint 的 tables 字段一致约定）
        tables_total += s.count("###")
    # 上次心跳: data_sources 表最新 created_at（暂以创建时间近似；真实 heartbeat 推 v0.6+）
    hb_row = conn.execute(
        "SELECT MAX(created_at) FROM data_sources WHERE is_active = 1"
    ).fetchone()
    conn.close()
    last_heartbeat = hb_row[0] if hb_row and hb_row[0] else None
    return {
        "total_schemas": schemas,
        "total_tables": tables_total,
        "last_heartbeat": last_heartbeat,
    }


# ─── v0.5.42 预算 demo 重构 — 单 global config（5 字段 app_settings KV）──────

class BudgetConfigRequest(BaseModel):
    monthly_token_cap: int      # 月度 token 上限（单组织全局）
    per_conv_token_cap: int     # 单次对话 token 上限（防 SQL planner 死循环）
    warn_pct: int               # 告警阈值百分比（0-100）
    default_model: str          # 默认模型
    rate_limit_per_min: int     # 单用户每分钟请求数限制


_BUDGET_DEFAULTS = {
    "budget_monthly_token_cap": "500000",
    "budget_per_conv_token_cap": "40000",
    "budget_warn_pct": "80",
    "budget_default_model": "claude-haiku-4-5",
    "budget_rate_limit_per_min": "20",
}


@router.get("/api/admin/budget-config")
async def admin_get_budget_config(admin=Depends(require_admin)):
    """v0.5.42 — 单 global 预算配置 5 字段（demo budget.jsx 模式）。"""
    return {
        "monthly_token_cap":   int(settings_repo.get_app_setting("budget_monthly_token_cap",   _BUDGET_DEFAULTS["budget_monthly_token_cap"])),
        "per_conv_token_cap":  int(settings_repo.get_app_setting("budget_per_conv_token_cap",  _BUDGET_DEFAULTS["budget_per_conv_token_cap"])),
        "warn_pct":            int(settings_repo.get_app_setting("budget_warn_pct",            _BUDGET_DEFAULTS["budget_warn_pct"])),
        "default_model":       settings_repo.get_app_setting("budget_default_model",            _BUDGET_DEFAULTS["budget_default_model"]),
        "rate_limit_per_min":  int(settings_repo.get_app_setting("budget_rate_limit_per_min",  _BUDGET_DEFAULTS["budget_rate_limit_per_min"])),
    }


@router.put("/api/admin/budget-config")
async def admin_update_budget_config(req: BudgetConfigRequest, request: Request, admin=Depends(require_admin)):
    """v0.5.42 — 保存 5 字段（app_settings KV upsert）。"""
    if req.monthly_token_cap < 1 or req.per_conv_token_cap < 1 or req.rate_limit_per_min < 1:
        raise HTTPException(status_code=400, detail="数值字段必须 ≥ 1")
    if req.warn_pct < 0 or req.warn_pct > 100:
        raise HTTPException(status_code=400, detail="告警阈值 0-100")
    settings_repo.set_app_setting("budget_monthly_token_cap",  str(req.monthly_token_cap))
    settings_repo.set_app_setting("budget_per_conv_token_cap", str(req.per_conv_token_cap))
    settings_repo.set_app_setting("budget_warn_pct",           str(req.warn_pct))
    settings_repo.set_app_setting("budget_default_model",      req.default_model)
    settings_repo.set_app_setting("budget_rate_limit_per_min", str(req.rate_limit_per_min))
    audit(request, "budget.config_update", "app_settings", "budget_config", success=True, detail=req.dict())
    return {"ok": True}
