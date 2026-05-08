"""bi_agent/api/audit.py — 审计列表与配置路由（v0.4.6 commit #3 + #5）。

红线：
- R-56 越权：require_admin（不是 get_current_user）
- R-61 强制分页：limit cap 200，超过自动截断（不抛错，兼容前端误传）
- R-49 retention 7~3650 区间校验
- R-57 meta-audit：retention_change 入 audit_log
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from bi_agent.api._audit_helpers import audit
from bi_agent.api.deps import require_admin
from bi_agent.repositories import audit_repo, settings_repo

router = APIRouter()


_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_RETENTION_KEY = "audit.retention_days"
_RETENTION_DEFAULT = 90
_RETENTION_MIN = 7
_RETENTION_MAX = 3650


@router.get("/api/admin/audit-log")
async def list_audit_log(
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    admin=Depends(require_admin),
):
    """admin 只读；强制分页（R-61 上限 200）。

    筛选支持 actor_id / action（精确匹配）/ resource_type / 时间窗口（since/until）。
    """
    limit = min(limit, _MAX_LIMIT)  # R-61 cap，不抛错（兼容前端误传 10000）
    if limit < 1:
        limit = _DEFAULT_LIMIT
    page = max(1, offset // max(limit, 1) + 1)
    rows = audit_repo.list_filtered(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        since=since,
        until=until,
        page=page,
        size=limit,
    )
    return {
        "items": rows,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
    }


@router.get("/api/admin/audit-config")
async def get_audit_config(admin=Depends(require_admin)):
    """R-49 retention 配置（默认 90 天）。"""
    raw = settings_repo.get_app_setting(_RETENTION_KEY, str(_RETENTION_DEFAULT))
    try:
        days = int(raw)
    except ValueError:
        days = _RETENTION_DEFAULT
    return {"retention_days": days, "min": _RETENTION_MIN, "max": _RETENTION_MAX}


@router.put("/api/admin/audit-config")
async def update_audit_config(payload: dict = Body(...), request: Request = None, admin=Depends(require_admin)):
    """R-49 + R-57 meta-audit：retention 调整本身入 audit_log。"""
    new_days = payload.get("retention_days")
    try:
        new_days = int(new_days)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="retention_days 必须是整数")
    if not (_RETENTION_MIN <= new_days <= _RETENTION_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"retention_days 必须在 {_RETENTION_MIN}~{_RETENTION_MAX} 区间",
        )
    old_raw = settings_repo.get_app_setting(_RETENTION_KEY, str(_RETENTION_DEFAULT))
    try:
        old_days = int(old_raw)
    except ValueError:
        old_days = _RETENTION_DEFAULT
    settings_repo.set_app_setting(_RETENTION_KEY, str(new_days))
    # R-57 meta-audit
    audit(request, admin, action="audit.retention_change", resource_type="audit",
          detail={"old": old_days, "new": new_days})
    return {"ok": True, "retention_days": new_days}
