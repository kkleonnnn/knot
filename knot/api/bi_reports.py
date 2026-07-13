"""bi_reports 路由（v0.8.5 ②a）— BI 模式报表 + 文件夹 CRUD + 刷新。

权限（R-BI-4）：
- 读（list folders/reports, get report）：`get_current_user`（全体已认证）
- 写（folder/report create/update/delete, refresh）：`require_admin`（analyst → 403）
非 admin 读报表 **不下发 sql_text**（R-BI-6，svc.to_dto）。

审计（R-BI-8）：每个 bi_report.* / report_folder.* Literal 均 `audit(request, admin, action=<常量>)`
直调 emit（AST 可抓；tests/api/test_metric_invariant_guards.py per-literal guard 断言）。

R-BI-1：与 saved_reports（ASK 收藏）严格分开 —— 全新路由前缀 /api/bi/，0 逻辑触碰。
"""
from __future__ import annotations

import asyncio
import json
import time
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import get_current_user, require_admin
from knot.repositories import bi_permission_repo
from knot.services import bi_permission_service as perm_svc
from knot.services import bi_report_service as svc
from knot.services.export_service import rows_to_csv_bytes, rows_to_xlsx_bytes, sheets_to_xlsx_bytes

router = APIRouter()


# ── Pydantic 请求模型（inline，镜像 saved_reports.py）────────────────────────────
class FolderCreateRequest(BaseModel):
    name: str
    parent_id: int | None = None
    sort_order: int = 0


class FolderUpdateRequest(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class ReportCreateRequest(BaseModel):
    title: str
    sql_text: str
    data_source_id: int | None = None
    folder_id: int | None = None
    report_type: str = "wide_table"
    column_config: dict | None = None
    overlay_config: list | None = None
    dashboard_config: dict | None = None
    tiles: list | None = None                 # ②b 仪表盘板块（每 tile 一条自己 SQL + 类型 + 布局）


class ReportUpdateRequest(BaseModel):
    title: str | None = None
    folder_id: int | None = None
    data_source_id: int | None = None         # v0.8.8：编辑可换/解绑数据源（此前缺 → builder 改数据源静默丢弃）
    sort_order: int | None = None
    sql_text: str | None = None
    column_config: dict | None = None
    overlay_config: list | None = None
    dashboard_config: dict | None = None
    tiles: list | None = None                 # 提供才 diff-by-id 同步（含 []=全删）；不提供=不动 tiles


class ReorderRequest(BaseModel):
    ordered_ids: list[int]                    # v0.8.8 ③：目录拖拽后的有序 id → sort_order=位置


class ReportAnalyzeRequest(BaseModel):
    question: str                             # v0.8.10 da-asst：用户对本报表的提问
    history: list[dict] = []                  # 既往对话 [{role, content}]（service 再截 12 轮）


class PermissionSetRequest(BaseModel):        # v0.8.12 RBAC：设一条 grant（按用户；folder_id / report_id 二选一）
    user_id: int
    folder_id: int | None = None
    report_id: int | None = None
    can_schedule: bool = False
    can_edit: bool = False
    can_export: bool = False
    can_share: bool = False


_MAX_OVERLAY_CELLS = 500  # overlay 单元格上限（防超大 overlay → 客户端求值 DoS；红队复验 residual）
_MAX_TILES = 30           # 仪表盘 tile 数上限（②b C-2；placement 同 overlay 在 api 层）
_MAX_REORDER = 1000       # reorder id 数上限（DoS 护栏；报表/文件夹不会近此量 —— 超即拒非静默截断）
_MAX_ANALYZE_HISTORY = 24 # da-asst 对话历史硬顶（防超大 payload；service 再 -12 轮 + 单条截断）


def _is_admin(user) -> bool:
    return user.get("role") == "admin"


def require_report_perm(action: str):
    """依赖工厂（v0.8.12 RBAC）：admin ∨ 当前用户对该报表有 <action> 权限，否则 403；报表不存在 404。
    返当前 user（handler 复用作 audit / created_by）。归档报表继承目录 grant、未分组查报表 grant（perm_svc）。"""
    def _dep(report_id: int, user=Depends(get_current_user)):
        r = svc.get_report(report_id)
        if not r:
            raise HTTPException(status_code=404, detail="报表不存在")
        if not perm_svc.can(user, r, action):
            raise HTTPException(status_code=403, detail="无该操作权限")
        return user
    return _dep


def _check_overlay_size(overlay) -> None:
    if isinstance(overlay, list) and len(overlay) > _MAX_OVERLAY_CELLS:
        raise HTTPException(status_code=400, detail=f"覆盖层单元格过多（≤{_MAX_OVERLAY_CELLS}）")


def _check_tiles_size(tiles) -> None:
    if not isinstance(tiles, list):
        return
    if len(tiles) > _MAX_TILES:
        raise HTTPException(status_code=400, detail=f"仪表盘板块过多（≤{_MAX_TILES}）")
    for t in tiles:      # v0.8.9：per-tile 公式行单元格上限（镜像 _MAX_OVERLAY_CELLS；防 viz_config 塞超大 overlay → 客户端求值 DoS）
        if not isinstance(t, dict):
            continue
        vc = t.get("viz_config")
        if not isinstance(vc, dict):   # 对抗复核 #4/#6：viz_config 可能是串/非 dict（service 容忍）→ 跳过不崩（防 500）
            continue
        ov = vc.get("overlay")
        if isinstance(ov, list) and len(ov) > _MAX_OVERLAY_CELLS:
            raise HTTPException(status_code=400, detail=f"公式行单元格过多（≤{_MAX_OVERLAY_CELLS}）")


def _check_reorder_size(ids) -> None:
    if len(ids) > _MAX_REORDER:
        raise HTTPException(status_code=400, detail=f"排序项过多（≤{_MAX_REORDER}）")


# ── 读（全体已认证；非 admin 脱 sql_text）────────────────────────────────────────

@router.get("/api/bi/folders")
async def list_folders(user=Depends(get_current_user)):
    return svc.list_folders()


@router.get("/api/bi/reports")
async def list_reports(user=Depends(get_current_user)):
    admin = _is_admin(user)
    return [svc.to_dto(r, admin) for r in svc.list_all()]


@router.get("/api/bi/reports/{report_id}")
async def get_report(report_id: int, user=Depends(get_current_user)):
    r = svc.get_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="报表不存在")
    # v0.8.12 C4b：附当前用户对本报表的 effective 权限 → 前端工具栏按 perm 显隐（后端仍强制，UI 只避免展示会 403 的按钮）
    return {**svc.to_dto(r, _is_admin(user)), "_perms": perm_svc.effective(user, r)}


@router.post("/api/bi/reports/{report_id}/analyze")
async def analyze_report(report_id: int, req: ReportAnalyzeRequest, request: Request,
                        user=Depends(get_current_user)):
    """da-asst 只读报表解读（v0.8.10）：基于报表**冻结快照**回答提问 —— 不写库、不跑新 SQL。

    读权限门 = `get_current_user`（与 get_report 一致）；非 admin 用脱敏 DTO（不含 sql_text）。
    **成本控制平面**（对齐 /api/query，防脚本 loop 财务 DoS + 花费不可见）：
    - LLM 调用前：月预算 pre-block（R-16/17，status=='block' → 402），over-budget 用户禁触发花费；
    - LLM 调用后：`update_user_usage` 记 input/output/cost → 入 user.monthly_cost_usd（可见 + 未来预算门有效）；
    - 每次 emit `bi_report.analyze` audit（花费归属 + R-BI-8 留痕）。
    LLM 领域异常（budget/auth/network，R-30）→ error_translator 翻译成 502 + user_message。
    """
    from knot.models.errors import KnotError
    from knot.repositories import user_repo
    from knot.services import budget_service, error_translator
    from knot.services.agents import da_asst

    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if len(req.history) > _MAX_ANALYZE_HISTORY:
        raise HTTPException(status_code=400, detail="对话历史过长")
    r = svc.get_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="报表不存在")
    status, _meta = budget_service.check_user_monthly_budget(user["id"])   # 月预算 pre-block
    if status == "block":
        raise HTTPException(status_code=402, detail="已达本月预算上限，暂停 AI 解读")
    dto = svc.to_dto(r, _is_admin(user))     # 非 admin 脱敏（不含 sql_text）→ da-asst 只见展示层快照
    t0 = time.time()
    try:
        out = await da_asst.arun_da_asst(dto, q, req.history)
    except KnotError as e:
        raise HTTPException(status_code=502, detail=error_translator.to_response(e)["user_message"]) from e
    # 记账（R-S8）：da-asst LLM 花费入 user 月度用量 → 可见 + 预算门下轮生效
    user_repo.update_user_usage(user["id"], out.get("input_tokens", 0), out.get("output_tokens", 0),
                                out.get("cost_usd", 0.0), int((time.time() - t0) * 1000))
    audit(request, user, action="bi_report.analyze", resource_type="bi_report",
          resource_id=report_id, detail={"cost_usd": round(out.get("cost_usd", 0.0), 6)})
    answer = out.get("answer") or ""
    if not answer:
        raise HTTPException(status_code=502, detail="分析未返回内容，请重试")
    return {"answer": answer}


# ── 写：报表（v0.8.12 RBAC —— edit 权限；admin 全权）─────────────────────────────────

@router.post("/api/bi/reports")
async def create_report(req: ReportCreateRequest, request: Request, user=Depends(get_current_user)):
    # RBAC：归档建报表需该目录 edit（admin 全权）；未分组建报表仅 admin（无 report_id 可授，can_folder 返 False）
    if not perm_svc.can_folder(user, req.folder_id, "edit"):
        raise HTTPException(status_code=403, detail="无该目录的建报表权限")
    _check_overlay_size(req.overlay_config)
    _check_tiles_size(req.tiles)
    try:
        r = svc.create_report(
            user, title=req.title, sql_text=req.sql_text, data_source_id=req.data_source_id,
            folder_id=req.folder_id, report_type=req.report_type,
            column_config=req.column_config, overlay_config=req.overlay_config,
            dashboard_config=req.dashboard_config, tiles=req.tiles,
        )
    except svc.SqlNotReadOnly as e:
        raise HTTPException(status_code=400, detail=f"SQL 未通过只读校验：{e}") from e
    audit(request, user, action="bi_report.create", resource_type="bi_report",
          resource_id=r["id"], detail={"title": r["title"], "data_source_id": req.data_source_id})
    return r


@router.put("/api/bi/reports/{report_id}")
async def update_report(report_id: int, req: ReportUpdateRequest, request: Request,
                       user=Depends(require_report_perm("edit"))):
    _check_overlay_size(req.overlay_config)
    _check_tiles_size(req.tiles)
    # model_fields_set：只透传显式提供的字段 → svc 默认（None=不改 / _UNSET=不改）保 folder/config/tiles 清空语义
    fields = req.model_fields_set
    kw = {k: getattr(req, k) for k in
          ("title", "folder_id", "data_source_id", "sort_order", "sql_text", "column_config", "overlay_config", "dashboard_config", "tiles")
          if k in fields}
    try:
        r = svc.update_report(report_id, admin=user, **kw)   # 供 diff-by-id 新 tile created_by（非 admin 编辑者亦可）
    except svc.SqlNotReadOnly as e:
        raise HTTPException(status_code=400, detail=f"SQL 未通过只读校验：{e}") from e
    if r is None:
        raise HTTPException(status_code=404, detail="报表不存在")
    audit(request, user, action="bi_report.update", resource_type="bi_report",
          resource_id=report_id, detail={"fields": sorted(kw.keys())})
    return r


@router.delete("/api/bi/reports/{report_id}")
async def delete_report(report_id: int, request: Request, user=Depends(require_report_perm("edit"))):
    if not svc.delete_report(report_id):
        raise HTTPException(status_code=404, detail="报表不存在")
    audit(request, user, action="bi_report.delete", resource_type="bi_report", resource_id=report_id)
    return {"ok": True}


@router.post("/api/bi/reports/{report_id}/refresh")
async def refresh_report(report_id: int, request: Request, user=Depends(require_report_perm("edit"))):
    # 卸载 sync SQLAlchemy 到线程池（dashboard N tile 查询串行，防阻塞事件循环）—— B-3/先例 datasources.py
    loop = asyncio.get_event_loop()
    out = await loop.run_in_executor(None, svc.refresh, report_id, user)
    if out is None:
        raise HTTPException(status_code=404, detail="报表不存在")
    # B-6：审计 detail 按 report_type 分支（dashboard/tabbed 返 per-tile summary，无顶层 rows/error）
    if out.get("report_type") in ("dashboard", "tabbed"):
        detail = {"tile_count": out.get("tile_count", 0), "error_count": out.get("error_count", 0)}
    else:
        detail = {"row_count": len(out.get("rows", [])), "error": bool(out.get("error"))}
    audit(request, user, action="bi_report.refresh", resource_type="bi_report",
          resource_id=report_id, detail=detail)
    return out


# ── 写：文件夹（require_admin）────────────────────────────────────────────────────

@router.post("/api/bi/folders")
async def create_folder(req: FolderCreateRequest, request: Request, admin=Depends(require_admin)):
    f = svc.create_folder(admin, name=req.name, parent_id=req.parent_id, sort_order=req.sort_order)
    audit(request, admin, action="report_folder.create", resource_type="report_folder",
          resource_id=f["id"], detail={"name": f["name"]})
    return f


@router.put("/api/bi/folders/{folder_id}")
async def update_folder(folder_id: int, req: FolderUpdateRequest, request: Request,
                       admin=Depends(require_admin)):
    fields = req.model_fields_set
    kw = {k: getattr(req, k) for k in ("name", "parent_id", "sort_order") if k in fields}
    f = svc.update_folder(folder_id, **kw)
    if f is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    audit(request, admin, action="report_folder.update", resource_type="report_folder",
          resource_id=folder_id, detail={"fields": sorted(kw.keys())})
    return f


@router.delete("/api/bi/folders/{folder_id}")
async def delete_folder(folder_id: int, request: Request, admin=Depends(require_admin)):
    if not svc.delete_folder(folder_id):
        raise HTTPException(status_code=404, detail="文件夹不存在")
    audit(request, admin, action="report_folder.delete", resource_type="report_folder", resource_id=folder_id)
    return {"ok": True}


# ── 目录拖拽排序（v0.8.8 ③；require_admin）——────────────────────────────────────
# 非碰撞前缀 /api/bi/reorder/*（不与 {report_id}/{folder_id} int 路径争路由）。
# 审计复用 bi_report.update / report_folder.update（sort_order 属更新语义 → 不新增 Literal）。

@router.put("/api/bi/reorder/reports")
async def reorder_reports(req: ReorderRequest, request: Request, admin=Depends(require_admin)):
    _check_reorder_size(req.ordered_ids)
    svc.reorder_reports(req.ordered_ids)
    audit(request, admin, action="bi_report.update", resource_type="bi_report",
          resource_id=None, detail={"fields": ["sort_order"], "reorder": len(req.ordered_ids)})
    return {"ok": True}


@router.put("/api/bi/reorder/folders")
async def reorder_folders(req: ReorderRequest, request: Request, admin=Depends(require_admin)):
    _check_reorder_size(req.ordered_ids)
    svc.reorder_folders(req.ordered_ids)
    audit(request, admin, action="report_folder.update", resource_type="report_folder",
          resource_id=None, detail={"fields": ["sort_order"], "reorder": len(req.ordered_ids)})
    return {"ok": True}


# ── 权限 RBAC 管理（v0.8.12；admin 授权角色×目录 / ×报表）─────────────────────────────

@router.get("/api/bi/permissions")
async def list_permissions(admin=Depends(require_admin)):
    """所有 grant（admin 管理 UI 渲染角色×资源矩阵）。"""
    return bi_permission_repo.list_all()


@router.put("/api/bi/permissions")
async def set_permission(req: PermissionSetRequest, request: Request, admin=Depends(require_admin)):
    """设一条 grant（folder_id / report_id 二选一）；4 权限全 0 = 撤销（删行）。emit bi_permission.change。"""
    if (req.folder_id is None) == (req.report_id is None):
        raise HTTPException(status_code=400, detail="folder_id / report_id 须且仅提供一个")
    perms = {"can_schedule": req.can_schedule, "can_edit": req.can_edit,
             "can_export": req.can_export, "can_share": req.can_share}
    if req.folder_id is not None:
        bi_permission_repo.set_folder_grant(req.user_id, req.folder_id, perms, admin["id"])
        target = {"folder_id": req.folder_id}
    else:
        bi_permission_repo.set_report_grant(req.user_id, req.report_id, perms, admin["id"])
        target = {"report_id": req.report_id}
    audit(request, admin, action="bi_permission.change", resource_type="bi_report",
          resource_id=req.folder_id or req.report_id or 0, detail={"user_id": req.user_id, **target, **perms})
    return {"ok": True}


# ── 导出（v0.8.12 收紧为 admin∨export 权限；复用 export_service —— CSV 注入中性化 v0.8.4，R-BI-12）──

def _report_or_404(report_id: int) -> dict:
    r = svc.get_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="报表不存在")
    return r


def _wide_rows_or_400(r: dict) -> list:
    try:
        rows = json.loads(r.get("last_run_rows_json") or "[]")
    except json.JSONDecodeError:
        rows = []
    if not rows:
        raise HTTPException(status_code=400, detail="该报表无可导出数据（请先重跑）")
    return rows


def _tile_sheet(tile: dict) -> dict:
    """tile → {name, rows, cols, headers}（列序=数据列 SQL 序；headers=viz_config.columns label 中文）。v0.8.9 导出。"""
    try:
        rows = json.loads(tile.get("last_run_rows_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        rows = []
    try:
        cfg = (json.loads(tile.get("viz_config") or "{}") or {}).get("columns") or {}
    except (json.JSONDecodeError, TypeError):
        cfg = {}
    cols = list(rows[0].keys()) if rows else list(cfg.keys())
    headers = [((cfg.get(c) or {}).get("label") or c) for c in cols]
    return {"name": tile.get("title") or "页", "rows": rows, "cols": cols, "headers": headers}


# dashboard = 图表板块（非表格）→ 不支持表格导出；tabbed = 多页表（Excel 多 sheet / CSV 单页）；wide_table = 单表。

@router.get("/api/bi/reports/{report_id}/export.csv")
async def export_report_csv(report_id: int, request: Request, tile_id: int | None = None,
                            user=Depends(require_report_perm("export"))):   # v0.8.12：收紧为 admin∨export 权限
    r = _report_or_404(report_id)
    rtype = r.get("report_type")
    if rtype == "dashboard":
        raise HTTPException(status_code=400, detail="仪表盘（图表板块）不支持表格导出")
    if rtype == "tabbed":
        tiles = r.get("tiles") or []
        if not tiles:
            raise HTTPException(status_code=400, detail="该报表无页签")
        tile = next((t for t in tiles if t.get("id") == tile_id), tiles[0])   # 当前页；未给取第一页
        sheet = _tile_sheet(tile)
        if not sheet["rows"]:
            raise HTTPException(status_code=400, detail="该页无可导出数据（请先重跑）")
        rows, cols, headers, stem = sheet["rows"], sheet["cols"], sheet["headers"], f"bi_report_{report_id}_{tile.get('id')}"
    else:
        rows, cols, headers, stem = _wide_rows_or_400(r), None, None, f"bi_report_{report_id}"
    audit(request, user, action="export.csv", resource_type="bi_report", resource_id=report_id,
          detail={"row_count": len(rows), "tile_id": tile_id})
    filename = f"{stem}.csv"
    return StreamingResponse(
        BytesIO(rows_to_csv_bytes(rows, cols=cols, headers=headers)), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/api/bi/reports/{report_id}/export.xlsx")
async def export_report_xlsx(report_id: int, request: Request, user=Depends(require_report_perm("export"))):   # v0.8.12：收紧为 admin∨export
    r = _report_or_404(report_id)
    rtype = r.get("report_type")
    if rtype == "dashboard":
        raise HTTPException(status_code=400, detail="仪表盘（图表板块）不支持表格导出")
    if rtype == "tabbed":
        sheets = [_tile_sheet(t) for t in (r.get("tiles") or [])]
        if not any(s["rows"] for s in sheets):
            raise HTTPException(status_code=400, detail="该报表各页均无可导出数据（请先重跑）")
        xlsx_bytes, meta = sheets_to_xlsx_bytes(sheets)          # 多 sheet：每页一 sheet
        total = sum(m["total"] for m in meta["sheets"])
        exported = sum(m["exported"] for m in meta["sheets"])
        truncated = meta["truncated"]
    else:
        rows = _wide_rows_or_400(r)
        xlsx_bytes, m = rows_to_xlsx_bytes(rows)
        total, exported, truncated = m["total"], m["exported"], m["truncated"]
    audit(request, user, action="export.xlsx", resource_type="bi_report", resource_id=report_id,
          detail={"row_count": total})
    filename = f"bi_report_{report_id}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Export-Truncated": "true" if truncated else "false",
            "X-Export-Total-Rows": str(total),
            "X-Export-Returned-Rows": str(exported),
        },
    )
