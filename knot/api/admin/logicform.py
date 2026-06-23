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
from knot.repositories import catalog_repo, conversation_repo, message_repo, semantic_audit_repo, user_repo

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


@router.post("/api/admin/logicform-audit/{audit_id}/rerun")
async def admin_rerun_logicform(audit_id: int, request: Request, admin=Depends(require_admin)):
    """admin 对审计行 re-run **真执行**（v0.7.4 C1 · F4 / R-SL-41~47）。

    从侧表行 logicform_json + catalog_id **重编译**（R-SL-40/47 原 catalog 烘焙；禁读 admin 当前 ContextVar）
    → D2-A 追溯**原 message 用户** engine（message→conv→user_id→get_user_engine；数据保真）
    → **必经 `db_connector.execute_query`**（R-SL-43 载体 `_is_safe_sql`：DQL-only / 单语句 / row-cap 收口，
      与 live 同源；**严禁裸连 conn.execute**；corrected filters 注入 `;` / DML 在此被拒）
    → 返 rows **临时**（R-SL-44 0 新 message 零污染）+ `logicform.rerun` audit（R-SL-42 executed_sql 四元组）。

    0 LLM（R-SL-45 纯编译 + execute，无 parser/presenter）。/correct 保持 compile-only（资深 v0.7.3 安全边界
    不动）；本端点是**独立 gate + 独立审计 + 真执行**能力。compile-fail / 原用户数据源不可用 → ok:False（不 audit rerun）。
    边界（R-SL-43）：containment = 只读单语句，**非**限定 metric 数据范围 —— admin 经 filter 可读数据源内任意
    只读子查询（= live 既有面 + admin 可信 + executed_sql 全审计兜底）。
    """
    import json

    from knot.adapters.db import doris as db_connector
    from knot.core import time_resolver
    from knot.services import query_helper
    from knot.services.engine_cache import get_user_engine
    from knot.services.semantic import compiler
    from knot.services.semantic.logicform import LogicForm

    orig = semantic_audit_repo.get_audit(audit_id)
    if orig is None:
        raise HTTPException(status_code=404, detail="审计行不存在")

    # R-SL-40/47 原 catalog 重编译（口径烘焙；与 /correct 同源；禁读 admin 当前 catalog）
    lf = LogicForm.from_dict(json.loads(orig["logicform_json"] or "{}"))
    row = catalog_repo.get_catalog(orig["catalog_id"])
    catalog = (query_helper._parse_catalog_content(row) if row
               else {"catalog_id": orig["catalog_id"], "tables": [], "relations": []})
    try:
        sql = compiler.compile_logicform(lf, catalog, time_resolver.resolve_time_context())
    except compiler.CompileError as e:
        return {"ok": False, "compile_error": str(e)}        # near-miss / 改坏 → admin 再调（不 audit rerun）

    # D2-A 原 message 用户 engine 追溯（数据保真：message→conv→user_id→get_user_engine，与 live 同解析）
    msg = message_repo.get_message(orig["message_id"])
    owner_id = conversation_repo.get_conversation_owner(msg["conversation_id"]) if msg else None
    owner = user_repo.get_user_by_id(owner_id) if owner_id else None
    if owner is None:
        return {"ok": False, "error": "原查询用户 / 会话不存在，无法追溯数据源"}
    engine, _schema = get_user_engine(owner)
    if engine is None:
        return {"ok": False, "error": "原用户数据源不可用（可能已改配置）"}   # R-SL-47 改源优雅降级

    # R-SL-43 真执行：必经 execute_query（顶部 _is_safe_sql DQL-only 收口；注入 filter 在此被拒）+ row cap 内建
    rows, db_error = db_connector.execute_query(engine, sql)

    # R-SL-42 审计四元组（executed_sql 入审计 — 兜底只读-任意-WHERE 边界）
    audit(request, admin, action="logicform.rerun", resource_type="logicform", resource_id=audit_id,
          detail={"message_id": orig["message_id"], "executed_sql": sql,
                  "row_count": len(rows), "db_error": db_error or ""})

    return {"ok": True, "sql": sql, "rows": rows, "row_count": len(rows), "db_error": db_error or ""}


@router.get("/api/admin/logicform-audit/{audit_id}/history")
async def admin_logicform_history(audit_id: int, admin=Depends(require_admin)):
    """版本历史（v0.7.5 · **read-only** / R-SL-49~56）：审计行 → 该 message 全版本链
    （原始 is_corrected=0 + 历次修正 is_corrected=1，ORDER BY id 时序 R-SL-53）。

    每版本 SQL **分层**（R-SL-51/56 保真度 — 守护者 Stage 3）：
    - **near-miss**（`compile_error_reason` 非空）→ 显**存的 reason 不重编译**（历史真相；重编译用当前
      metric 会复现可能不同的 error / 现成功 → 失真）。
    - **hit**（reason 空）→ 重编译原 catalog（R-SL-40）取 SQL，前端标注「当前重编译」非原始；现失败
      （metric 漂移/删 → CompileError）→ try-except → kind=hit_recompile_failed，**与历史 near-miss 区分**。

    **LogicForm（canonical_json）才是忠实历史源**（diff 主体，每版本原样回传）；SQL 仅当前渲染。
    read-only：0 mutation / 0 新 message / 0 新侧表行 / 不发 audit（看演化非治理事件 R-SL-50）。
    """
    import json

    from knot.core import time_resolver
    from knot.services import query_helper
    from knot.services.semantic import compiler
    from knot.services.semantic.logicform import LogicForm

    orig = semantic_audit_repo.get_audit(audit_id)
    if orig is None:
        raise HTTPException(status_code=404, detail="审计行不存在")

    versions = semantic_audit_repo.list_by_message(orig["message_id"])   # 全版本链（R-SL-53）
    row = catalog_repo.get_catalog(orig["catalog_id"])                   # R-SL-40 原 catalog 一次解析（全版本同 catalog_id）
    catalog = (query_helper._parse_catalog_content(row) if row
               else {"catalog_id": orig["catalog_id"], "tables": [], "relations": []})
    time_ctx = time_resolver.resolve_time_context()

    out = []
    for v in versions:
        entry = {
            "audit_id": v["id"], "is_corrected": v["is_corrected"],
            "created_at": v["created_at"], "parent_message_id": v["parent_message_id"],
            "logicform_json": v["logicform_json"],          # 忠实历史源（diff 主体 R-SL-56）
        }
        if v["compile_error_reason"]:
            # near-miss：显存的 reason 不重编译（R-SL-51 历史真相）
            entry.update(kind="near_miss", reason=v["compile_error_reason"])
        else:
            # hit：重编译取当前 SQL（R-SL-56 前端标注「当前重编译」）；现失败 → 区分历史 near-miss
            try:
                lf = LogicForm.from_dict(json.loads(v["logicform_json"] or "{}"))
                entry.update(kind="hit", sql=compiler.compile_logicform(lf, catalog, time_ctx))
            except compiler.CompileError as e:
                entry.update(kind="hit_recompile_failed", reason=str(e))   # 口径可能已变更
        out.append(entry)
    return out
