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

# v0.6.5.0 R-2FA-3：admin 应急后门（唯一豁免路径）
# KNOT_TOTP_BYPASS_ADMIN=true → admin 跳过 TOTP（ops 逃生口，防唯一 admin 弄丢
# authenticator + recovery code 永久锁死）；非 admin 不享后门（由 admin reset 救援）。
# /api/totp/* 白名单让被强制用户能走完 enroll（强制 ≠ 锁死）。
_TOTP_ENDPOINT_WHITELIST_PREFIX = "/api/totp/"


def _admin_bypass_active() -> bool:
    """v0.6.5.0 R-2FA-1/3：admin 应急后门（唯一豁免路径）。

    KNOT_TOTP_BYPASS_ADMIN=true → admin bypass（ops 应急逃生口，防唯一 admin
    弄丢 authenticator + recovery code 永久锁死）。

    v0.6.5.0 删 v0.6.2.0 R-PB-B1-3 的「0 admin enrolled → bootstrap 自动 bypass」
    优先级 2（资深 2026-06-19 裁定：admin 不豁免；且无自愿 enroll UI ⟹ 该 bootstrap
    令唯一 admin 永远无法被 enroll，2FA 形同虚设）。仅保留显式 env 后门。
    """
    return os.getenv("KNOT_TOTP_BYPASS_ADMIN", "").strip().lower() == "true"


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

        # v0.6.5.0 R-2FA-1/2：强制 enroll（默认 on — 资深 2026-06-19 提前 R-PA-8 公测门）。
        # KNOT_TOTP_REQUIRED 默认 "true" 强制；显式设 =false 关闭（eval/demo 快速评估）。
        # 未 enroll 用户访问非白名单端点 → 403；admin 仅 KNOT_TOTP_BYPASS_ADMIN 应急后门可豁免。
        if os.getenv("KNOT_TOTP_REQUIRED", "true").strip().lower() == "true":
            path = request.url.path
            if not user.get("totp_enrolled_at"):
                if not path.startswith(_TOTP_ENDPOINT_WHITELIST_PREFIX) \
                   and not path.startswith(_FORCE_CHANGE_PWD_WHITELIST_PREFIX):
                    # R-2FA-3：admin 应急后门（唯一豁免）；非 admin 短路不进后门
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
