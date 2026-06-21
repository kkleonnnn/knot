"""knot/api/admin/budgets.py — 预算管理路由（admin.py 拆分 v0.6.5.11）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.repositories import budget_repo, settings_repo
from knot.services import budget_service

router = APIRouter()


# ── Budgets (v0.4.3 R-18/R-21) ─────────────────────────────────────────

class BudgetUpsertRequest(BaseModel):
    scope_type: str       # 'user' | 'agent_kind' | 'global'
    scope_value: str      # user_id (str) | agent_kind | 'all'
    budget_type: str      # 'monthly_cost_usd' | 'monthly_tokens' | 'per_call_cost_usd'
    threshold: float
    action: str = "warn"  # 'warn' | 'block'（block 仅 agent_kind/per_call）
    enabled: int = 1


class BudgetUpdateRequest(BaseModel):
    threshold: float | None = None
    action: str | None = None
    enabled: int | None = None


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
    "budget_default_model": "anthropic/claude-haiku-4.5",  # v0.6.5.4 OR-only（旧悬空 'claude-haiku-4-5' 不在 MODELS）
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
    audit(request, admin, action="config.budget_update", resource_type="budget",
          resource_id="budget_config", success=True, detail=req.dict())
    return {"ok": True}
