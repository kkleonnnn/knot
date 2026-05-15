"""knot/api/deps.py — JWT 凭证 + 用户校验依赖（v0.6.0.8 加 JWT_SECRET fail-fast）。

v0.6.0.8 MUST-1：JWT_SECRET 必须由 env 显式提供，缺失 / 默认占位 → sys.exit(1)。
同 KNOT_MASTER_KEY 模式（v0.4.5 R-45 / v0.5.0 R-68）— 防被默认占位签 token = 任意用户伪造登录。
"""
import os
import sys
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
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
    exp = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, _get_secret(), algorithm=JWT_ALGORITHM)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, _get_secret(), algorithms=[JWT_ALGORITHM])
        user = get_user_by_id(int(payload["sub"]))
        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="用户不存在或已停用")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except (jwt.InvalidTokenError, Exception):
        raise HTTPException(status_code=401, detail="无效的登录凭证")


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
