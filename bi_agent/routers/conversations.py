from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

import persistence
from ..dependencies import get_current_user
from ..schemas import CreateConversationRequest

router = APIRouter()


@router.get("/api/conversations")
async def list_conversations(user=Depends(get_current_user)):
    return persistence.list_conversations(user["id"])


@router.post("/api/conversations")
async def create_conversation(req: CreateConversationRequest, user=Depends(get_current_user)):
    cid = persistence.create_conversation(user["id"], req.title)
    return {"id": cid, "title": req.title, "updated_at": datetime.now().isoformat()}


@router.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int, user=Depends(get_current_user)):
    convs = persistence.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)
    persistence.delete_conversation(conv_id)
    return {"ok": True}


@router.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: int, user=Depends(get_current_user)):
    convs = persistence.list_conversations(user["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=404)
    return persistence.get_messages(conv_id)
