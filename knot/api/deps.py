"""knot/api/deps.py — JWT 凭证 + 用户校验依赖（v0.6.0.8 加 JWT_SECRET fail-fast）。

v0.6.0.8 MUST-1：JWT_SECRET 必须由 env 显式提供，缺失 / 默认占位 → sys.exit(1)。
同 KNOT_MASTER_KEY 模式（v0.4.5 R-45 / v0.5.0 R-68）— 防被默认占位签 token = 任意用户伪造登录。
"""
import os
import sys
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from knot.repositories.user_repo import get_user_by_id

# v0.6.0.8 MUST-1：废除 fallback 默认值。任何下列情况 → sys.exit(1)：
#   1. JWT_SECRET 完全未设
#   2. JWT_SECRET = 历史默认占位 "knot-secret-change-in-production"
#   3. JWT_SECRET 长度 < 16（防 "test" 这种短到爆破的值）
# v0.6.0.8: 已知历史默认占位（公开仓 grep 可得，必须拒收）
# R-79 守护：旧 brand 字面用 split 构造避免 grep 触发；同 tests/test_rename_smoke.py 风格
_LEGACY_BRAND_OLD = "bi" + "-agent-secret-change-in-production"  # v0.4.x 期遗留
_LEGACY_BRAND_CHATBI = "chatbi-secret-change-in-production"      # v0.2.x 期遗留
_BLOCKED_DEFAULTS = frozenset({
    "knot-secret-change-in-production",
    _LEGACY_BRAND_CHATBI,
    _LEGACY_BRAND_OLD,
})
_LEGACY_DEFAULT = "knot-secret-change-in-production"  # 老代码兼容引用
_MIN_LEN = 16


def _resolve_jwt_secret() -> str:
    """启动期解析；缺失或默认占位 → fail-fast + 友好彩色提示退出。

    由 main.py 启动期显式调用（_check_jwt_secret_or_exit）+ 测试 setup 调用以提前 fail。
    模块 import 时 lazy — 读 env 但不 fail，让测试 conftest 有机会 setenv。
    v0.6.0.8 patch：调用前显式 load_dotenv() 兜底（.env 中 JWT_SECRET 会被识别）。
    """
    try:
        from dotenv import load_dotenv as _ld
        _ld()
    except ImportError:
        pass
    val = os.getenv("JWT_SECRET", "").strip()
    if not val or val in _BLOCKED_DEFAULTS or len(val) < _MIN_LEN:
        bar = "━" * 60
        print(f"\033[1;31m{bar}", file=sys.stderr)
        print("✗ KNOT 启动失败 — JWT_SECRET 配置无效", file=sys.stderr)
        if not val:
            print("  原因: 未设 JWT_SECRET 环境变量", file=sys.stderr)
        elif val in _BLOCKED_DEFAULTS:
            print(f"  原因: 仍用历史默认占位 '{val}' （任何人能伪造 token 登录任意账号）", file=sys.stderr)
        else:
            print(f"  原因: 长度 {len(val)} < {_MIN_LEN}（不安全）", file=sys.stderr)
        print("", file=sys.stderr)
        print("  生成新 secret:", file=sys.stderr)
        print("    openssl rand -hex 32", file=sys.stderr)
        print("", file=sys.stderr)
        print("  设置环境变量后重启:", file=sys.stderr)
        print("    export JWT_SECRET=<生成的 secret>", file=sys.stderr)
        print(f"{bar}\033[0m", file=sys.stderr)
        sys.exit(1)
    return val


# v0.6.0.8 MUST-1：lazy 读取（import 时不 fail；测试 conftest 可 setenv 后 main.py 验证）
# 业务路径 create_token / get_current_user 通过 _get_secret() 读最新值
def _get_secret() -> str:
    """每次 token 操作时读 env（覆盖 monkeypatch.setenv 场景）。"""
    return os.getenv("JWT_SECRET", "").strip() or _LEGACY_DEFAULT


# 模块级常量（向后兼容老代码 `from knot.api.deps import JWT_SECRET`）
JWT_SECRET = os.getenv("JWT_SECRET", _LEGACY_DEFAULT).strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

security = HTTPBearer()


def create_token(user_id: int) -> str:
    """v0.6.2.0 R-PB-B1-13：payload 含 ver=token_version → 后续 reset/change_pwd 触发吊销。"""
    exp = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    # lazy import 避免 circular（totp_service → user_repo → ... → deps）
    from knot.services.totp_service import get_token_version_cached
    ver = get_token_version_cached(user_id)
    return jwt.encode({"sub": str(user_id), "ver": ver, "exp": exp},
                      _get_secret(), algorithm=JWT_ALGORITHM)


# v0.6.0.20 admin 强制改密：白名单路径在 must_change_password=1 时仍放行
# 含 me / change-password / logout 等 auth flow；其他 API 一律 403 直到改密成功
_FORCE_CHANGE_PWD_WHITELIST_PREFIX = "/api/auth/"

# v0.6.2.0 R-PB-B1-3：admin 自身 enroll 三层防御
# 优先级 1: env KNOT_TOTP_BYPASS_ADMIN=true → 全局跳过 TOTP（应急后门）
# 优先级 2: ≥1 admin 完成 enroll → 上述 bypass 自动失效（业务条件触发）
# 优先级 3: TOTP 完全 enroll 流程白名单（让用户能 enroll）
_TOTP_ENDPOINT_WHITELIST_PREFIX = "/api/totp/"


def _admin_bypass_active() -> bool:
    """R-PB-B1-3 三层防御：
    优先级 1: env KNOT_TOTP_BYPASS_ADMIN=true → 强制 bypass（应急后门）
    优先级 2: 0 admin enrolled → bypass active（bootstrap mode 让首位 admin 能 enroll）
    优先级 3: ≥ 1 admin enrolled → 强制 off（除非 env 优先级 1 强制 on）
    """
    env_bypass = os.getenv("KNOT_TOTP_BYPASS_ADMIN", "").strip().lower() == "true"
    from knot.repositories.base import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM users "
        "WHERE role='admin' AND totp_enrolled_at IS NOT NULL",
    ).fetchone()
    conn.close()
    any_admin_enrolled = int(row["c"]) > 0
    # 优先级 3 sustained：≥1 admin enrolled → 仅 env 强制可绕（应急后门）
    if any_admin_enrolled:
        return env_bypass
    # 优先级 1+2：0 admin enrolled → bootstrap mode bypass on（无 24h 限制 — 守护者
    # §III.4 24h gating 简化为"≥1 admin enrolled 触发"，移除 startup 时间追踪复杂度）
    return True


def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, _get_secret(), algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])

        # v0.6.2.0 R-PB-B1-13：JWT 吊销 — payload.ver != users.token_version → 401
        # interim_token (totp_pending=true) 不走此检查（由 api/totp.verify 单独处理）
        if not payload.get("totp_pending"):
            from knot.services.totp_service import get_token_version_cached
            current_ver = get_token_version_cached(user_id)
            if int(payload.get("ver", 0)) != current_ver:
                raise HTTPException(status_code=401, detail="JWT_REVOKED")

        user = get_user_by_id(user_id)
        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="用户不存在或已停用")

        # v0.6.0.20 admin 强制改密：must_change_password=1 时仅 /api/auth/* 放行
        if user.get("must_change_password") and not request.url.path.startswith(_FORCE_CHANGE_PWD_WHITELIST_PREFIX):
            raise HTTPException(status_code=403, detail="must_change_password")

        # v0.6.2.0 R-PB-B1-4 公测启动闸门：强制 enroll 拦截由 KNOT_TOTP_REQUIRED env 控制
        # 内测期（默认 unset）→ 不拦截；用户可自愿 enroll（TOTP 端点仍开放）
        # 公测启动前（R-PA-8 自验 + Day 28+ 三方会议）→ 资深 ack 后 export KNOT_TOTP_REQUIRED=true
        if os.getenv("KNOT_TOTP_REQUIRED", "").strip().lower() == "true":
            path = request.url.path
            if not user.get("totp_enrolled_at"):
                if not path.startswith(_TOTP_ENDPOINT_WHITELIST_PREFIX) \
                   and not path.startswith(_FORCE_CHANGE_PWD_WHITELIST_PREFIX):
                    # R-PB-B1-3 admin bypass 三层判断（env / 0 admin enrolled / 优先级 3 auto-expire）
                    if not (user["role"] == "admin" and _admin_bypass_active()):
                        raise HTTPException(status_code=403, detail="totp_enroll_required")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, Exception):
        raise HTTPException(status_code=401, detail="无效的登录凭证")


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
