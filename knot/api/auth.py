from fastapi import APIRouter, Depends, HTTPException, Request

from knot import config as cfg
from knot.api._audit_helpers import audit
from knot.api._rate_limit import rate_limit_change_pwd, rate_limit_login
from knot.api.deps import create_token, get_current_user
from knot.api.schemas import ChangePasswordRequest, LoginRequest
from knot.services import auth_service

router = APIRouter()


# v0.6.0.23 — login rate limit（10 次/60s/IP）防字典攻击；与 v0.6.0.20 admin
# 强制改密互补：强制改密把默认密码漏洞补上，rate limit 把暴力破解关口收窄
@router.post("/api/auth/login", dependencies=[Depends(rate_limit_login)])
async def login(req: LoginRequest, request: Request):
    username = req.username.strip()
    user = auth_service.authenticate(username, req.password)
    if not user:
        # D5：失败登录记尝试的 username（暴力破解检测）；actor=None 因身份未知
        audit(request, actor=None, action="auth.login_fail",
              resource_type="user", success=False,
              detail={"attempted_username": username})
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    audit(request, actor=user, action="auth.login_success",
          resource_type="user", resource_id=user["id"])

    # v0.6.2.0 R-PB-B1-9：login 成功 + totp_enrolled → interim_token（短期，仅 verify）
    # 用户必须再走 /api/totp/verify 提供 6 位码才能拿完整 JWT。
    if user.get("totp_enrolled_at"):
        from knot.api.totp import create_interim_token
        return {
            "need_totp": True,
            "interim_token": create_interim_token(user["id"], int(user.get("token_version", 1))),
            # 不返完整 user — verify 通过后再返
        }

    return {
        "token": create_token(user["id"]),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "role": user["role"],
            # v0.6.0.20 admin 强制改密：前端见 true 弹 ForceChangePassword 模态
            "must_change_password": bool(user.get("must_change_password")),
        },
    }


@router.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"] or user["username"],
        "role": user["role"],
        "preferred_model": user.get("preferred_model") or cfg.DEFAULT_MODEL,
        # v0.6.0.20 admin 强制改密：me 也回，方便刷新页面后前端拿到最新状态
        "must_change_password": bool(user.get("must_change_password")),
    }


@router.post("/api/auth/change-password",
             dependencies=[Depends(rate_limit_change_pwd)])
async def change_password(req: ChangePasswordRequest, request: Request,
                          user=Depends(get_current_user)):
    """v0.6.0.20 修改密码 + 解除 must_change_password 守护。

    业务规则见 services/auth_service.change_password：
    - 旧密码必须匹配
    - 新密码 ≥ 8 字符 + 不复用默认值 + 不等于旧密码

    被 must_change_password=1 屏蔽的用户仍可调本端点（get_current_user 白名单豁免）。
    """
    ok, msg = auth_service.change_password(user["id"], req.old_password, req.new_password)
    audit(request, actor=user,
          action="user.password_reset",
          resource_type="user", resource_id=user["id"],
          success=ok,
          detail={"reason": msg} if not ok else None)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    # v0.6.2.0 R-PB-B1-13 + γ1 顺手安全债：change_password 必 bump token_version → 旧 JWT 立即 401
    from knot.services import totp_service
    totp_service.bump_token_version_only(user["id"])
    return {"ok": True, "message": msg}
