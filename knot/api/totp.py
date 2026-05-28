"""totp api — v0.6.2.0 TOTP 2FA 4 端点 + interim_token 流程。

红线落地（commit 3 范围 — R-PB-B1-3/6/9/13）：
- R-PB-B1-3：admin 三层防御 — 在 deps.py + main.py 启动期；本文件不动
- R-PB-B1-6：enforce_totp_verify_rate_limit / enforce_totp_enroll_rate_limit
- R-PB-B1-9 Session 验证补充：login 成功 + totp_enrolled → interim_token（短期，仅含 verify 权限）
- R-PB-B1-13：reset 必 invalidate_token_version_cache + bump_token_version_in_tx（service 内已落）

interim_token 设计（区别于完整 JWT）：
- payload = {"sub": user_id, "totp_pending": true, "exp": now+5min, "ver": token_version}
- 仅 /api/totp/verify 接受；其他端点拒绝（防绕过 TOTP 直接拿 interim 调业务接口）
- verify 通过后 → 颁发完整 JWT（含 totp_verified=true）
"""
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request

from knot.api._audit_helpers import audit
from knot.api._rate_limit import (
    enforce_totp_enroll_rate_limit,
    enforce_totp_verify_rate_limit,
)
from knot.api.deps import (
    JWT_ALGORITHM,
    _get_secret,
    create_token,
    get_current_user,
    require_admin,
)
from knot.api.schemas import (
    TotpEnrollCompleteRequest,
    TotpResetRequest,
    TotpVerifyRequest,
)
from knot.services import totp_service

router = APIRouter()

# interim_token：5 分钟有效期 — 用户扫码后慢慢输入也够（业界标准）
_INTERIM_EXPIRE_MIN = 5


def create_interim_token(user_id: int, token_version: int) -> str:
    """login 成功 + totp_enrolled 后颁发 — 仅 /api/totp/verify 接受。"""
    exp = datetime.utcnow() + timedelta(minutes=_INTERIM_EXPIRE_MIN)
    return jwt.encode(
        {"sub": str(user_id), "totp_pending": True, "ver": token_version, "exp": exp},
        _get_secret(), algorithm=JWT_ALGORITHM,
    )


def _decode_interim(token: str) -> dict:
    """仅本文件 verify 端点使用 — payload.totp_pending 必为 True。"""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[JWT_ALGORITHM])
        if not payload.get("totp_pending"):
            raise HTTPException(status_code=401, detail="非 interim token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="TOTP 验证窗口超时，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 interim token")


# ─── 4 端点 ────────────────────────────────────────────────────────────


@router.post("/api/totp/enroll-init")
async def enroll_init(request: Request, user=Depends(get_current_user)):
    """Step 1：生成 secret + QR otpauth:// URI + 内联 PNG data URL（不持久化）。

    返 {secret, qr_uri, qr_dataurl} — 前端 <img src={qr_dataurl}> 直接展示 QR。
    qr_dataurl 服务端生成（qrcode lib commit 1 sustained）避免前端 npm 依赖。
    R-PB-B1-6 rate limit：enroll 3/hour/user 防恶意频繁。
    """
    enforce_totp_enroll_rate_limit(user["id"])
    secret, qr_uri = totp_service.enroll_init(user["id"])
    # v0.6.2.0 commit 5：QR PNG 内联 base64 data URL（commit 1 qrcode[pil] dep sustained）
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(qr_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_dataurl = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"secret": secret, "qr_uri": qr_uri, "qr_dataurl": qr_dataurl}


@router.post("/api/totp/enroll-complete")
async def enroll_complete(req: TotpEnrollCompleteRequest, request: Request,
                          user=Depends(get_current_user)):
    """Step 2：1 次动态码验证（R-PB-B1-7）+ R-46-Tx 事务持久化。

    返 {recovery_codes} — 前端必须强制下载才能完成 enroll（前端 commit 5 落地）。
    成功 → audit user.totp.enroll
    """
    enforce_totp_enroll_rate_limit(user["id"])
    codes = totp_service.enroll_complete(user["id"], req.secret, req.code)
    if not codes:
        audit(request, actor=user, action="user.totp.verify_failed",
              resource_type="user", resource_id=user["id"], success=False,
              detail={"phase": "enroll"})
        raise HTTPException(status_code=400, detail="验证码错误，请重新扫码后再试")
    audit(request, actor=user, action="user.totp.enroll",
          resource_type="user", resource_id=user["id"])
    return {"recovery_codes": codes}


@router.post("/api/totp/verify")
async def verify(req: TotpVerifyRequest, request: Request):
    """login 后 verify — interim_token + 6 位码 → 完整 JWT（含 totp_verified）。

    R-PB-B1-6 rate limit：5/min/user（解析 interim 拿 user_id 后限流）。
    R-PB-B1-9 Session 验证：verify 失败不颁发完整 JWT；interim 仍有效但只能用于 verify。
    """
    payload = _decode_interim(req.interim_token)
    user_id = int(payload["sub"])
    enforce_totp_verify_rate_limit(user_id)

    # recovery code 兜底（10-char 含 "-" 自动识别 — 与 6 位 TOTP 冲突小）
    is_recovery = "-" in req.code and len(req.code) >= 10
    ok = (totp_service.consume_recovery(user_id, req.code) if is_recovery
          else totp_service.verify(user_id, req.code))

    from knot.repositories.user_repo import get_user_by_id
    user = get_user_by_id(user_id)
    if not ok:
        audit(request, actor=user, action="user.totp.verify_failed",
              resource_type="user", resource_id=user_id, success=False,
              detail={"recovery": is_recovery})
        raise HTTPException(status_code=401, detail="TOTP 验证失败")

    if is_recovery:
        audit(request, actor=user, action="user.totp.recovery_code_used",
              resource_type="user", resource_id=user_id,
              detail={"phase": "login_recovery"})

    # 颁发完整 JWT（含当前 token_version；后续业务请求 deps.py 验证）
    full_token = create_token(user_id)
    return {
        "token": full_token,
        "user": {
            "id": user["id"], "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "role": user["role"],
            "must_change_password": bool(user.get("must_change_password")),
        },
    }


@router.post("/api/totp/reset")
async def reset(req: TotpResetRequest, request: Request,
                admin=Depends(require_admin)):
    """admin 重置 user TOTP — R-PB-B1-5：audit + recovery_codes 全清 + token_version +1。

    R-PB-B1-13：reset 必触发被重置用户的旧 JWT 立即 401（cache invalidate +
    DB token_version +1，下次请求 deps.py 验证不匹配）。
    """
    totp_service.reset(req.target_user_id)
    audit(request, actor=admin, action="user.totp.reset",
          resource_type="user", resource_id=req.target_user_id)
    return {"ok": True, "message": "TOTP 已重置，用户下次登录需重新 enroll"}
