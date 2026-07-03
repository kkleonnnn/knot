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
    # v0.6.0.3 F-A：传 viewer_user_id 让 repo LEFT JOIN feedback 回显当前用户态度
    msgs = message_repo.get_messages(conv_id, viewer_user_id=user["id"])
    # v0.4.1.1: API 边界 normalization — 与 SSE final 事件对齐（query.py emit 的是 'sql'）。
    # 修复历史消息回放时前端 ResultBlock 解构 msg.sql 拿不到值导致 ⭐ 收藏按钮缺失。
    for m in msgs:
        m["sql"] = m.get("sql_text")
    # v0.6.0.17 — 非 admin 用户脱敏：移除 sql_text + sql 字段（防内部表名泄漏给业务用户）
    # admin 保留完整字段用于调试 + 业务目录维护
    if user.get("role") != "admin":
        for m in msgs:
            m.pop("sql_text", None)
            m.pop("sql", None)
        # v0.6.0.19 脱敏链 3/3 + v0.7.35（B1.2 R-B1.2-11/12）：文本中业务表全名 → 业务别名。
        #   - 字段集扩至 explanation/db_error/error/insight（desensitize_messages_for_non_admin 经
        #     scrub_query_payload 单一真相源 — 保 reload ≈ 硬化后 live SSE 一致，否则 reload 反 under-scrub）
        #   - lexicon 源改 per-user active catalog（current_catalog；非全局 LEXICON — 非默认 catalog 用户
        #     alias_map 才完整）；get_messages 原不 capture → 此处 set per-user active catalog ContextVar
        #     （请求作用域，FastAPI 每请求独立 Task + copy_context 天然不泄漏 R-PB-A1-22）
        # 延迟 import 避免启动期循环（services → api 单向依赖；本调用是 api 内层）
        from knot.services import query_helper
        from knot.services.agents import catalog as catalog_loader
        from knot.services.desensitize import desensitize_messages_for_non_admin
        query_helper.capture_active_catalog(user)
        desensitize_messages_for_non_admin(msgs, catalog_loader.current_catalog().get("lexicon"))
    return msgs
