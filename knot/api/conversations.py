from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

# v0.3.0: import persistence → 直接 import 各 repo（保留"persistence.X"调用形态）
from knot.api.deps import get_current_user
from knot.api.schemas import CreateConversationRequest
from knot.repositories import conversation_repo, message_repo

router = APIRouter()


@router.get("/api/conversations")
async def list_conversations(user=Depends(get_current_user)):
    return conversation_repo.list_conversations(user["id"])


@router.post("/api/conversations")
async def create_conversation(req: CreateConversationRequest, user=Depends(get_current_user)):
    cid = conversation_repo.create_conversation(user["id"], req.title)
    return {"id": cid, "title": req.title, "updated_at": datetime.now().isoformat()}


@router.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int, user=Depends(get_current_user)):
    convs = conversation_repo.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)
    conversation_repo.delete_conversation(conv_id)
    return {"ok": True}


@router.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: int, user=Depends(get_current_user)):
    convs = conversation_repo.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)
    msgs = message_repo.get_messages(conv_id)
    # v0.4.1.1: API 边界 normalization — 与 SSE final 事件对齐（query.py emit 的是 'sql'）。
    # 修复历史消息回放时前端 ResultBlock 解构 msg.sql 拿不到值导致 ⭐ 收藏按钮缺失。
    for m in msgs:
        m["sql"] = m.get("sql_text")
    return msgs
