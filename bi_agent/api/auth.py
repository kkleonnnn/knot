from fastapi import APIRouter, Depends, HTTPException

from bi_agent import config as cfg
from bi_agent.api.deps import create_token, get_current_user
from bi_agent.api.schemas import LoginRequest
from bi_agent.services import auth_service

router = APIRouter()


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    user = auth_service.authenticate(req.username.strip(), req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
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
