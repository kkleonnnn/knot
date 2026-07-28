from fastapi import APIRouter, Depends, HTTPException, Request

from knot import config as cfg
from knot.api._audit_helpers import audit
from knot.api._rate_limit import rate_limit_change_pwd, rate_limit_login
from knot.api.deps import create_token, get_current_user
from knot.api.schemas import ChangePasswordRequest, LoginRequest
from knot.core.logging_setup import logger
from knot.core.tenant_context import (
    TenantContextError,
    clear_active_tenant,
    reset_active_tenant,
    set_active_tenant,
)
from knot.repositories import tenant_repo
from knot.services import auth_service

router = APIRouter()


# ⭐ v0.9.4 D4'/kk 决策②：**五个失败分支共用同一句**（代号不存在 / 租户停用 / 用户不存在 /
# 用户停用 / 口令错）。任何可区分的差异 = **公司枚举 / 账号枚举**。
# 「读得到的差异」由本常量堵住；「耗时差异」由 `auth_service.consume_password_time` 堵住（缺一不可）。
_LOGIN_FAIL_MSG = "账号或密码错误"


def _resolve_login_tenant(company: str | None) -> dict | None:
    """登录**自建 ctx** 的第一步：按公司代号（ctx-free，读平台库）定位租户；不可服务 → `None`。

    kk 决策①「每家公司一条专属登录链接」：链接带 `?c=<slug>`，前端回传到请求体 `company`。

    ⚠️ **未带代号时回退到「唯一 active 租户」—— 这是有条件的临时允许，不是通则**：
    - 允许的**唯一理由**：R-T-GATE 仍硬锁第二租户（每请求 `assert_no_second_active_tenant_served`）
      ⇒ 单租户下「唯一 active」与「按代号解析」等价。
    - **已登记 R-T-GATE 就绪清单：lift 前必须把 `company` 改为必填**，否则回退就变成
      「不带代号 → 随便进某家公司」= OOS-1v2 fail-open。
    - 之所以现在不直接必填：会把**当前**内测部署的所有人挡在门外（老链接无 `?c=`）。

    0 active 租户 → `resolve_single_tenant` raise → 折成 `None` → 统一 401
    （D5 明示：此处**不得 500**，否则「整站崩」与「密码错」可区分，且运维排障时被误导为 bug）。
    """
    slug = (company or "").strip()
    if slug:
        return tenant_repo.resolve_tenant_by_slug(slug)
    try:
        return tenant_repo.resolve_single_tenant()
    except TenantContextError:
        return None


# v0.6.0.23 — login rate limit（10 次/60s/IP）防字典攻击；与 v0.6.0.20 admin
# 强制改密互补：强制改密把默认密码漏洞补上，rate limit 把暴力破解关口收窄
@router.post("/api/auth/login", dependencies=[Depends(rate_limit_login)])
async def login(req: LoginRequest, request: Request):
    """v0.9.4 D4''-③：**自建 ctx** 端点 —— 入口无条件清 ctx，再从请求内容决定租户。

    为何入口必须清（R-13）：前端 axios 拦截器会把**陈旧 Authorization** 带到登录请求上（B-5），
    middleware 可能据此把 ctx 设成**别的公司**。清掉后 ctx 为 None ⇒ 「清 ctx 到 set-ctx 之间误用
    上游 ctx」会**当场崩**而不是静默串租户（R-13 是运行期自执行的，不靠静态清单）。
    `rate_limit_login` 是 IP 桶（`_rate_limit._enforce`，不碰 ctx）⇒ 它在 Depends 里先跑无妨。
    """
    username = req.username.strip()
    entry_tok = clear_active_tenant()                       # ① R-13 入口不变量
    try:
        tenant = _resolve_login_tenant(req.company)         # ② ctx-free（读平台库）
        if tenant is None:
            # 分支①②：代号不存在 / 租户停用。**没有租户库可写审计** —— 平台侧审计尚不存在
            # （已登记 R-T-GATE 清单「平台侧审计 + tenants.updated_at」）⇒ 此处只能落日志。
            # 只记代号，不记口令/用户名以外的东西；代号本身是攻击者已知的输入。
            auth_service.consume_password_time(req.password)   # 耗时对齐（否则可枚举公司）
            logger.info(f"[login] 未知或停用的公司代号 company={(req.company or '')[:40]!r} → 统一 401")
            raise HTTPException(status_code=401, detail=_LOGIN_FAIL_MSG)

        tenant_tok = set_active_tenant(tenant)              # ③ 建 ctx（此后一切在 ctx 内）
        try:
            return _login_within_tenant(req, request, username)
        finally:
            reset_active_tenant(tenant_tok)
    finally:
        reset_active_tenant(entry_tok)


def _login_within_tenant(req: LoginRequest, request: Request, username: str):
    """ctx 已建之后的登录主体（分支③④⑤ + 成功路径）—— 拆出仅为让上面的 ctx 作用域一眼可读。"""
    user, reason = auth_service.authenticate_with_reason(username, req.password)
    if user is None:
        # D5：失败登录记尝试的 username（暴力破解检测）；actor=None 因身份未知。
        # `reason` 只进审计 detail，**绝不进响应**（进了就是账号枚举）。
        audit(request, actor=None, action="auth.login_fail",
              resource_type="user", success=False,
              detail={"attempted_username": username, "reason": reason})
        raise HTTPException(status_code=401, detail=_LOGIN_FAIL_MSG)
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
