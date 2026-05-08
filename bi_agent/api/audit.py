"""bi_agent/api/audit.py — 审计列表与配置路由（v0.4.6 commit #3）。

红线：
- R-56 越权：require_admin（不是 get_current_user）
- R-61 强制分页：limit cap 200，超过自动截断（不抛错，兼容前端误传）
"""
from typing import Optional

from fastapi import APIRouter, Depends

from bi_agent.api.deps import require_admin
from bi_agent.repositories import audit_repo

router = APIRouter()


_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


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
