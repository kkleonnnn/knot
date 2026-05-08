from fastapi import APIRouter, Depends, HTTPException, Request

from bi_agent import config as cfg
from bi_agent.api._audit_helpers import audit
from bi_agent.api.deps import create_token, get_current_user
from bi_agent.api.schemas import LoginRequest
from bi_agent.services import auth_service

router = APIRouter()


@router.post("/api/auth/login")
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
    return {
        "token": create_token(user["id"]),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "role": user["role"],
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
    }
