"""knot/api/admin/logicform.py — LogicForm 审计/修正 admin 路由（v0.7.3 C2 list + C3 修正）。

全 require_admin（继承 2FA enroll gate）；LogicForm/SQL 仅 admin 审计面（脱敏链 sustained，非 admin 不可见）。
审计行来自 semantic_query_audit 侧表（命中 + near-miss）；enrich message 的 question/sql 供展示。
catalog 隔离（R-SL-39/40）：list 按 catalog_id 过滤。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from knot.api.deps import require_admin
from knot.repositories import message_repo, semantic_audit_repo

router = APIRouter()


@router.get("/api/admin/logicform-audit")
async def admin_list_logicform_audit(catalog_id: int | None = None, admin=Depends(require_admin)):
    """语义路径查询审计：LogicForm + 编译 SQL + 问题 + 命中/near-miss 状态。

    审计「AI 如何理解每个查询」（read-only）。命中 = compile_error_reason 空；near-miss = 有回退原因。
    catalog_id 给定则仅该 catalog（R-SL-39/40 隔离）。
    """
    rows = semantic_audit_repo.list_audit(catalog_id)
    out = []
    for r in rows:
        msg = message_repo.get_message(r["message_id"]) or {}
        out.append({
            **r,
            "question": msg.get("question", ""),
            "sql": msg.get("sql_text", ""),
            "hit": not r["compile_error_reason"],   # 命中 = 无编译错误（near-miss = 有回退原因）
        })
    return out
