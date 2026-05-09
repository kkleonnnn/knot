"""导出路由（v0.4.0 CSV；v0.4.2 加 xlsx）。

权限模型：必须是该 message 所属 conversation 的所有者；admin 例外可下载任何 message。
"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from knot.api.deps import get_current_user
from knot.repositories import conversation_repo, message_repo
from knot.services.export_service import rows_to_csv_bytes, rows_to_xlsx_bytes

router = APIRouter()


def _check_message_access(message_id: int, user) -> dict:
    """共用权限校验：返回 msg dict 或 raise 404 防 id 枚举。"""
    msg = message_repo.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")
    owner_id = conversation_repo.get_conversation_owner(msg["conversation_id"])
    is_admin = user.get("role") == "admin"
    if owner_id != user["id"] and not is_admin:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")
    return msg


@router.get("/api/messages/{message_id}/export.csv")
async def export_message_csv(message_id: int, user=Depends(get_current_user)):
    """导出某条 message 的 rows 为 CSV。

    404 — 消息不存在 / 无权访问
    400 — 该消息无 rows 可导出
    """
    msg = _check_message_access(message_id, user)
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


@router.get("/api/messages/{message_id}/export.xlsx")
async def export_message_xlsx(message_id: int, user=Depends(get_current_user)):
    """v0.4.2：导出 message rows 为 xlsx（5000 行硬限）。

    R-S7：截断信息通过响应头暴露给前端：
      X-Export-Truncated: true|false
      X-Export-Total-Rows: <int>
      X-Export-Returned-Rows: <int>
    前端据此 toast 「已截断至 N 行（共 M 行）」。
    """
    msg = _check_message_access(message_id, user)
    rows = msg.get("rows") or []
    if not rows:
        raise HTTPException(status_code=400, detail="该消息无可导出数据")

    xlsx_bytes, meta = rows_to_xlsx_bytes(rows)
    filename = f"export_msg{message_id}.xlsx"
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
