from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

# v0.3.0: import persistence → 直接 import 各 repo（保留"persistence.X"调用形态）
from ..dependencies import get_current_user
from ..schemas import CreateConversationRequest
from bi_agent.repositories import conversation_repo
from bi_agent.repositories import message_repo

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
    return message_repo.get_messages(conv_id)
