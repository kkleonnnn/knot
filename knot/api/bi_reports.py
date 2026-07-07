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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import get_current_user, require_admin
from knot.services import bi_report_service as svc

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


class ReportUpdateRequest(BaseModel):
    title: str | None = None
    folder_id: int | None = None
    sort_order: int | None = None
    sql_text: str | None = None
    column_config: dict | None = None
    overlay_config: list | None = None


_MAX_OVERLAY_CELLS = 500  # overlay 单元格上限（防超大 overlay → 客户端求值 DoS；红队复验 residual）


def _is_admin(user) -> bool:
    return user.get("role") == "admin"


def _check_overlay_size(overlay) -> None:
    if isinstance(overlay, list) and len(overlay) > _MAX_OVERLAY_CELLS:
        raise HTTPException(status_code=400, detail=f"覆盖层单元格过多（≤{_MAX_OVERLAY_CELLS}）")


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
    return svc.to_dto(r, _is_admin(user))


# ── 写：报表（require_admin）──────────────────────────────────────────────────────

@router.post("/api/bi/reports")
async def create_report(req: ReportCreateRequest, request: Request, admin=Depends(require_admin)):
    _check_overlay_size(req.overlay_config)
    try:
        r = svc.create_report(
            admin, title=req.title, sql_text=req.sql_text, data_source_id=req.data_source_id,
            folder_id=req.folder_id, report_type=req.report_type,
            column_config=req.column_config, overlay_config=req.overlay_config,
        )
    except svc.SqlNotReadOnly as e:
        raise HTTPException(status_code=400, detail=f"SQL 未通过只读校验：{e}") from e
    audit(request, admin, action="bi_report.create", resource_type="bi_report",
          resource_id=r["id"], detail={"title": r["title"], "data_source_id": req.data_source_id})
    return r


@router.put("/api/bi/reports/{report_id}")
async def update_report(report_id: int, req: ReportUpdateRequest, request: Request,
                       admin=Depends(require_admin)):
    _check_overlay_size(req.overlay_config)
    # model_fields_set：只透传显式提供的字段 → svc 默认（None=不改 / _UNSET=不改）保 folder/config 清空语义
    fields = req.model_fields_set
    kw = {k: getattr(req, k) for k in
          ("title", "folder_id", "sort_order", "sql_text", "column_config", "overlay_config")
          if k in fields}
    try:
        r = svc.update_report(report_id, **kw)
    except svc.SqlNotReadOnly as e:
        raise HTTPException(status_code=400, detail=f"SQL 未通过只读校验：{e}") from e
    if r is None:
        raise HTTPException(status_code=404, detail="报表不存在")
    audit(request, admin, action="bi_report.update", resource_type="bi_report",
          resource_id=report_id, detail={"fields": sorted(kw.keys())})
    return r


@router.delete("/api/bi/reports/{report_id}")
async def delete_report(report_id: int, request: Request, admin=Depends(require_admin)):
    if not svc.delete_report(report_id):
        raise HTTPException(status_code=404, detail="报表不存在")
    audit(request, admin, action="bi_report.delete", resource_type="bi_report", resource_id=report_id)
    return {"ok": True}


@router.post("/api/bi/reports/{report_id}/refresh")
async def refresh_report(report_id: int, request: Request, admin=Depends(require_admin)):
    out = svc.refresh(report_id, admin)
    if out is None:
        raise HTTPException(status_code=404, detail="报表不存在")
    audit(request, admin, action="bi_report.refresh", resource_type="bi_report",
          resource_id=report_id,
          detail={"row_count": len(out.get("rows", [])), "error": bool(out.get("error"))})
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
