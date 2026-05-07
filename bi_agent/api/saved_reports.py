"""saved_reports 路由（v0.4.1）— pin / list / run / update / delete + CSV 导出。

权限模型：
- pin from message : 必须是 conversation owner OR admin（同 v0.4.0 message 导出）
- list             : 仅看自己的
- run/update/delete: owner OR admin
- 非所有者一律 404 防 id 枚举（不暴露 403）

R-12 幂等：pin 同 message 二次返 200 + already_pinned=true，前端按钮变 🌟。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bi_agent.api.deps import get_current_user
from bi_agent.repositories import conversation_repo, message_repo
from bi_agent.services import saved_report_service

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
async def pin_from_message(message_id: int, req: PinRequest, user=Depends(get_current_user)):
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
    return {**sr, "already_pinned": already}


@router.post("/api/saved-reports/{report_id}/run")
async def run_saved_report(report_id: int, user=Depends(get_current_user)):
    result = saved_report_service.run(report_id, user)
    if result is None:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    return result


@router.put("/api/saved-reports/{report_id}")
async def update_saved_report(report_id: int, req: UpdateSavedReportRequest, user=Depends(get_current_user)):
    sr = saved_report_service.update_owned(report_id, user, title=req.title, pin_note=req.pin_note)
    if sr is None:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    return sr


@router.delete("/api/saved-reports/{report_id}")
async def delete_saved_report(report_id: int, user=Depends(get_current_user)):
    ok = saved_report_service.delete_owned(report_id, user)
    if not ok:
        raise HTTPException(status_code=404, detail="报表不存在或无权访问")
    return {"ok": True}
