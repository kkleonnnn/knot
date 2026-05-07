"""导出路由（v0.4.0 仅 CSV；v0.4.1 计划加 xlsx）。

权限模型：必须是该 message 所属 conversation 的所有者；admin 例外可下载任何 message。
"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from bi_agent.api.deps import get_current_user
from bi_agent.repositories import conversation_repo, message_repo
from bi_agent.services.export_service import rows_to_csv_bytes

router = APIRouter()


@router.get("/api/messages/{message_id}/export.csv")
async def export_message_csv(message_id: int, user=Depends(get_current_user)):
    """导出某条 message 的 rows 为 CSV。

    404 — 消息不存在 / 无权访问
    400 — 该消息无 rows 可导出
    """
    msg = message_repo.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")

    owner_id = conversation_repo.get_conversation_owner(msg["conversation_id"])
    is_admin = user.get("role") == "admin"
    if owner_id != user["id"] and not is_admin:
        # 不区分"无权"与"不存在"，避免 message_id 枚举
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")

    rows = msg.get("rows") or []
    if not rows:
        raise HTTPException(status_code=400, detail="该消息无可导出数据")

    csv_bytes = rows_to_csv_bytes(rows)
    filename = f"export_msg{message_id}.csv"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return StreamingResponse(
        BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
