"""knot/api/admin/logicform.py — LogicForm 审计/修正 admin 路由（v0.7.3 C2 list + C3 修正）。

全 require_admin（继承 2FA enroll gate）；LogicForm/SQL 仅 admin 审计面（脱敏链 sustained，非 admin 不可见）。
审计行来自 semantic_query_audit 侧表（命中 + near-miss）；enrich message 的 question/sql 供展示。
catalog 隔离（R-SL-39/40）：list 按 catalog_id 过滤。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import require_admin
from knot.repositories import catalog_repo, message_repo, semantic_audit_repo

router = APIRouter()


class CorrectRequest(BaseModel):
    logicform: dict   # 修正后的 LogicForm（admin 改 AI 理解，如 dimension city→channel）


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


@router.post("/api/admin/logicform-audit/{audit_id}/correct")
async def admin_correct_logicform(audit_id: int, req: CorrectRequest, request: Request,
                                  admin=Depends(require_admin)):
    """admin 修正 LogicForm → **原 catalog 重编译**（R-SL-40 audit.catalog_id；不同 catalog 同名 metric 口径不同）
    → 返修正 SQL + 落审计血缘行（is_corrected=1 / parent_message_id）+ logicform.correct audit（R-SL-37/38）。

    v0.7.3 scope (a) 重编译 only（确定性展示「改 LogicForm → SQL 变成 X」，比改 SQL 友好）；
    **不重执行**（re-run 需引擎解析 → 留 v0.7.4）。修正后仍编译失败 → 返 ok:False（admin 再调，不落血缘）。
    """
    from knot.core import time_resolver
    from knot.services import query_helper
    from knot.services.semantic import compiler
    from knot.services.semantic.logicform import LogicForm

    orig = semantic_audit_repo.get_audit(audit_id)
    if orig is None:
        raise HTTPException(status_code=404, detail="审计行不存在")
    lf = LogicForm.from_dict(req.logicform)
    row = catalog_repo.get_catalog(orig["catalog_id"])           # R-SL-40 原 catalog 重解析
    catalog = (query_helper._parse_catalog_content(row) if row
               else {"catalog_id": orig["catalog_id"], "tables": [], "relations": []})
    try:
        sql = compiler.compile_logicform(lf, catalog, time_resolver.resolve_time_context())
    except compiler.CompileError as e:
        return {"ok": False, "compile_error": str(e)}            # 修正后仍编译失败 → admin 再调（不落血缘）
    new_aid = semantic_audit_repo.create_audit(
        message_id=orig["message_id"], catalog_id=orig["catalog_id"],
        logicform_json=lf.to_canonical_json(), is_corrected=1, parent_message_id=orig["message_id"],
    )
    audit(request, admin, action="logicform.correct", resource_type="logicform", resource_id=new_aid,
          detail={"parent_audit_id": audit_id, "message_id": orig["message_id"]})
    return {"ok": True, "sql": sql, "audit_id": new_aid}
