"""saved_reports 路由（v0.4.1）— pin / list / run / update / delete + CSV 导出。

权限模型：
- pin from message : 必须是 conversation owner OR admin（同 v0.4.0 message 导出）
- list             : 仅看自己的
- run/update/delete: owner OR admin
- 非所有者一律 404 防 id 枚举（不暴露 403）

R-12 幂等：pin 同 message 二次返 200 + already_pinned=true，前端按钮变 🌟。
"""
import json
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from knot.api._audit_helpers import audit
from knot.api.deps import get_current_user
from knot.repositories import conversation_repo, message_repo
from knot.services import saved_report_service
from knot.services.export_service import rows_to_csv_bytes, rows_to_xlsx_bytes

router = APIRouter()


class PinRequest(BaseModel):
    title: Optional[str] = None
    pin_note: Optional[str] = None


class UpdateSavedReportRequest(BaseModel):
    title: Optional[str] = None
    pin_note: Optional[str] = None


@router.get("/api/saved-reports")
async def list_saved_reports(user=Depends(get_current_user)):
    return saved_report_service.list_for_user(user)


@router.post("/api/messages/{message_id}/pin")
async def pin_from_message(message_id: int, req: PinRequest, request: Request, user=Depends(get_current_user)):
    """从 message 创建 saved_report。R-12 幂等：重复 pin 返 200 + already_pinned=true。"""
    msg = message_repo.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")
    owner_id = conversation_repo.get_conversation_owner(msg["conversation_id"])
    is_admin = user.get("role") == "admin"
    if owner_id != user["id"] and not is_admin:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")
    if not msg.get("sql_text"):
        raise HTTPException(status_code=400, detail="该消息无可收藏的 SQL（澄清/失败消息无法收藏）")

    sr, already = saved_report_service.create_from_message(
        user, msg, title=req.title, pin_note=req.pin_note,
    )
    if not already:
        audit(request, user, action="saved_report.pin", resource_type="saved_report",
              resource_id=sr["id"], detail={"source_message_id": message_id, "title": sr.get("title")})
    return {**sr, "already_pinned": already}


@router.post("/api/saved-reports/{report_id}/run")
async def run_saved_report(report_id: int, request: Request, user=Depends(get_current_user)):
    result = saved_report_service.run(report_id, user)
    if result is None:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    audit(request, user, action="saved_report.run", resource_type="saved_report",
          resource_id=report_id, detail={"row_count": len(result.get("rows", []))})
    return result


@router.put("/api/saved-reports/{report_id}")
async def update_saved_report(report_id: int, req: UpdateSavedReportRequest, request: Request, user=Depends(get_current_user)):
    sr = saved_report_service.update_owned(report_id, user, title=req.title, pin_note=req.pin_note)
    if sr is None:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    audit(request, user, action="saved_report.update", resource_type="saved_report",
          resource_id=report_id,
          detail={"fields": [k for k, v in {"title": req.title, "pin_note": req.pin_note}.items() if v is not None]})
    return sr


@router.delete("/api/saved-reports/{report_id}")
async def delete_saved_report(report_id: int, request: Request, user=Depends(get_current_user)):
    ok = saved_report_service.delete_owned(report_id, user)
    if not ok:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    audit(request, user, action="saved_report.delete", resource_type="saved_report",
          resource_id=report_id)
    return {"ok": True}


@router.get("/api/saved-reports/{report_id}/export.csv")
async def export_saved_report_csv(report_id: int, user=Depends(get_current_user)):
    """导出 saved_report 最近一次重跑的 rows 为 CSV（复用 v0.4.0 export_service）。

    400 — 该报表无 rows 可导出（请先调 /run）
    404 — 报表不存在 / 无权访问
    """
    sr = saved_report_service.get_owned(report_id, user)
    if not sr:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    rows_json = sr.get("last_run_rows_json") or "[]"
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        rows = []
    if not rows:
        raise HTTPException(status_code=400, detail="该报表无可导出数据（请先重跑）")

    csv_bytes = rows_to_csv_bytes(rows)
    filename = f"saved_report_{report_id}.csv"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return StreamingResponse(
        BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/api/saved-reports/{report_id}/export.xlsx")
async def export_saved_report_xlsx(report_id: int, user=Depends(get_current_user)):
    """v0.4.2 xlsx 导出（5000 行硬限）。

    R-S7：截断信息通过响应头 X-Export-Truncated / X-Export-Total-Rows /
    X-Export-Returned-Rows 暴露给前端，由前端 toast 提示。
    """
    sr = saved_report_service.get_owned(report_id, user)
    if not sr:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    rows_json = sr.get("last_run_rows_json") or "[]"
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        rows = []
    if not rows:
        raise HTTPException(status_code=400, detail="该报表无可导出数据（请先重跑）")

    xlsx_bytes, meta = rows_to_xlsx_bytes(rows)
    filename = f"saved_report_{report_id}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "X-Export-Truncated":     "true" if meta["truncated"] else "false",
        "X-Export-Total-Rows":    str(meta["total"]),
        "X-Export-Returned-Rows": str(meta["exported"]),
    }
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
