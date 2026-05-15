"""v0.6.0.3 F-A — 用户对每条 assistant 回答的反馈（👍/👎 + 可选评论）。

设计：
- POST /api/messages/{message_id}/feedback {score: +1|-1, comment?: str}
    - score 必须 ±1；comment 可选 ≤ 500 char
    - 同 user × 同 message UNIQUE 触发 upsert（用户回头反悔可改）
    - M-A5：审计 feedback.submit
- GET /api/admin/feedback?score=&limit=&offset=
    - admin 全局列表 + 分页（limit cap 200 R-61）

权限：复用 exports._check_message_access — 只能反馈自己 conversation 的 message；admin 可反馈任意。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from knot.api._audit_helpers import audit
from knot.api.deps import get_current_user, require_admin
from knot.api.exports import check_message_access
from knot.repositories import feedback_repo

router = APIRouter()

_MAX_COMMENT_LEN = 500


class FeedbackBody(BaseModel):
    score: int = Field(..., description="+1 (good) or -1 (bad)")
    comment: str = Field("", max_length=_MAX_COMMENT_LEN)


@router.post("/api/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    body: FeedbackBody,
    request: Request,
    user=Depends(get_current_user),
):
    """提交对单条 assistant 回答的 +1/-1 反馈 + 可选评论。

    422 — score 非 ±1（Pydantic 不做枚举，运行时校验）/ comment 超长
    404 — 消息不存在或越权（复用 exports access 链）
    """
    if body.score not in (-1, 1):
        raise HTTPException(status_code=422, detail="score 必须为 +1 或 -1")
    # 权限 + 存在性校验（404 防 id 枚举）
    check_message_access(message_id, user)
    rid = feedback_repo.upsert(
        message_id=message_id, user_id=user["id"],
        score=body.score, comment=(body.comment or "").strip(),
    )
    # M-A5 审计 — fail-soft（audit_service 内部 try/except）
    audit(request, user,
          action="feedback.submit",
          resource_type="message",
          resource_id=str(message_id),
          detail={"score": body.score, "has_comment": bool(body.comment)})
    return {"id": rid, "score": body.score}


@router.get("/api/messages/{message_id}/feedback")
async def get_my_feedback(
    message_id: int,
    user=Depends(get_current_user),
):
    """查询当前用户对该消息的反馈（前端历史对话回显态度）。"""
    check_message_access(message_id, user)
    rec = feedback_repo.get_by_message_user(message_id, user["id"])
    if not rec:
        return {"score": None, "comment": ""}
    return {"score": rec["score"], "comment": rec.get("comment", "")}


@router.get("/api/admin/feedback")
async def admin_list_feedback(
    score: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    admin=Depends(require_admin),
):
    """admin 全局反馈列表 + 分页。

    score: 1 / -1 / None(all)
    R-61 limit cap 200 (repo enforced)
    """
    if score is not None and score not in (-1, 1):
        raise HTTPException(status_code=422, detail="score 必须为 +1 / -1 / 不传")
    items = feedback_repo.list_admin(score=score, limit=limit, offset=offset)
    total = feedback_repo.count_admin(score=score)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
