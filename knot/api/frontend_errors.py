"""v0.6.0.4 F-B — 前端 JS 错误上报。

设计：
- POST /api/frontend-errors (user token；未登录页可走 anon token 但暂不支持)
- GET  /api/admin/frontend-errors (admin only + top hashes)

PII 防御（M-B2）：
- 后端 _redact_free_text 应用 4 类正则：手机号 / 身份证 / 邮箱 / 已知 API key 模式
- 严格 ≤ 上限长度（_repo 内 _MAX_* 已 trim）
- 不审计（避免 audit_log 也含 PII；F-B 本身就是观测渠道）
"""
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from knot.api.deps import get_current_user, require_admin
from knot.repositories import frontend_error_repo

router = APIRouter()

# M-B2 PII 正则（free-text 通用脱敏 — 与 audit_service._scrub 字段名层互补）
_PII_PATTERNS = [
    (re.compile(r"\b1[3-9]\d{9}\b"),                       "<phone>"),       # 大陆手机
    (re.compile(r"\b\d{17}[\dXx]\b"),                       "<id>"),         # 大陆身份证
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),              "<api_key>"),    # OpenAI / Anthropic
    (re.compile(r"\bsk-ant-api03-[A-Za-z0-9_-]{20,}\b"),    "<api_key>"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),             "<api_key>"),    # Google
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),               "<api_key>"),    # GitHub
    (re.compile(r"\benc_v1:[A-Za-z0-9_=-]{40,}\b"),         "<enc_v1>"),     # 自家 Fernet 密文
]


def _redact_free_text(s: str) -> str:
    """对自由文本应用 PII 正则；返回脱敏后的字符串。"""
    if not s:
        return s
    out = s
    for pat, repl in _PII_PATTERNS:
        out = pat.sub(repl, out)
    return out


class FrontendErrorBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    stack: str = Field("", max_length=10000)
    url: str = Field("", max_length=500)
    error_hash: str = Field("", max_length=64)


@router.post("/api/frontend-errors")
async def submit_frontend_error(
    body: FrontendErrorBody,
    request: Request,
    user=Depends(get_current_user),
):
    """前端 JS 错误上报。

    M-B1 throttle 在前端做（hash dedupe + 1h cooldown + 1min cap 5）；
    后端不再 throttle（防 attacker spoofing hashes 绕过）。
    M-B2 PII redact 后端兜底（不依赖前端）。
    """
    msg = _redact_free_text(body.message)
    stk = _redact_free_text(body.stack)
    ua = (request.headers.get("user-agent") or "")[:500]
    rid = frontend_error_repo.insert(
        user_id=user["id"],
        message=msg,
        stack=stk,
        url=body.url,
        user_agent=ua,
        error_hash=body.error_hash or None,
    )
    return {"id": rid, "ok": True}


@router.get("/api/admin/frontend-errors")
async def admin_list_frontend_errors(
    limit: int = 100,
    offset: int = 0,
    admin=Depends(require_admin),
):
    """admin 全局错误列表 + top hashes 聚合。"""
    items = frontend_error_repo.list_admin(limit=limit, offset=offset)
    total = frontend_error_repo.count_admin()
    top = frontend_error_repo.top_hashes(limit=10)
    return {"items": items, "total": total, "limit": limit, "offset": offset, "top_hashes": top}
