"""bi_agent/api/_audit_helpers.py — API 边界审计 helper（v0.4.6）。

api 层 helper 复用模式（与 v0.4.5 `_secret.py` 同模式 — 不污染 services）：
- `_get_client_ip(request)`：处理 X-Forwarded-For / X-Real-IP 反代场景
- `audit(request, actor, **kwargs)`：从 Request 自动取 ip / user_agent / request_id

R-58 守护：client_ip / user_agent / request_id 是 audit 第三要素，
由本 helper 在 api 边界收集，service 层不必关心 Request 对象。
"""
from __future__ import annotations

from fastapi import Request

from bi_agent.services import audit_service


def _get_client_ip(request: Request) -> str:
    """守护者前瞻：优先取 X-Forwarded-For 最左 IP（真实客户端），
    fallback X-Real-IP，再 fallback request.client.host。

    nginx / cloudflare 反代场景下 request.client.host = 反代 IP，
    必须从 header 取真实客户端。
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # 取最左（真实客户端）；后续是反代链
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else ""


def audit(request: Request, actor: dict | None, **kwargs) -> None:
    """API 层 helper：自动从 request 取 client_ip / user_agent / request_id。

    R-47 fail-soft 由 audit_service.log 内部保证；本 helper 不再重复 try/except。
    """
    audit_service.log(
        actor=actor,
        client_ip=_get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
        **kwargs,
    )
