"""totp_service — v0.6.2.0 TOTP 2FA 强制 enroll 核心安全模块。

红线落地（R-PB-B1-1 ~ R-PB-B1-13 + NRP-1/2）：
- R-PB-B1-1/8：secret Fernet 加密（透明 — 由 user_repo._USER_ENCRYPTED_COLS 处理）
- R-PB-B1-9 R-46-Tx：enroll_complete + reset 走单一 SQLite 事务
                     （secret + recovery_codes + token_version 任一失败全回滚）
- R-PB-B1-10 + NRP-2：verify 单步长 mock 时间锁定（测试侧守护）
- R-PB-B1-11：4 audit_action（enroll / verify_failed / reset / recovery_code_used）
- R-PB-B1-12：pyotp.TOTP(secret).verify(code, valid_window=1) ±30 秒容忍
- R-PB-B1-13 + NRP-1：cachetools.TTLCache(maxsize=10000, ttl=60)
                     reset / change_password 时 cache.pop(user_id) — 不用 lru_cache

KNOT 元数据架构（v4 §0.3 sustained）：
- TOTP 数据全在 SQLite (knot.db) — 严禁跨 Doris 事务。
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime

import bcrypt
import pyotp
from cachetools import TTLCache

from knot.repositories import totp_repo, user_repo

# ─── R-PB-B1-13 + NRP-1：JWT token_version cache（TTLCache，单 user 失效）─
_TOKEN_VERSION_CACHE: TTLCache = TTLCache(maxsize=10000, ttl=60)

# ─── v0.6.5.2 F4-back：2FA rollout 一次性 session 失效标志（app_settings KV）──
_ROLLOUT_FLAG_KEY = "totp_rollout_session_invalidated"

# bcrypt for recovery code hash — 与 auth_service.hash_password 同精神（直接 bcrypt，
# 不走 passlib.CryptContext 避免 bcrypt 4.x detect_wrap_bug ValueError 兼容问题）

# Recovery codes：10 个 × 10 chars (base32 大写 + 短横连字增强可读性 e.g., "ABCDE-12345"）
_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_BYTES = 6  # → 10 base32 chars after stripping padding


def _utc_iso() -> str:
    """统一时间戳格式 — audit + last_used_at 用。"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ─── R-PB-B1-13：token_version 查询 + cache 失效 ───────────────────────


def get_token_version_cached(user_id: int) -> int:
    """JWT 验证调用 — cache hit 直接返；miss 走 DB + cache 60s。"""
    cached = _TOKEN_VERSION_CACHE.get(user_id)
    if cached is not None:
        return int(cached)
    ver = user_repo.get_token_version(user_id)
    _TOKEN_VERSION_CACHE[user_id] = ver
    return ver


def invalidate_token_version_cache(user_id: int) -> None:
    """R-PB-B1-13 NRP-1：reset / change_password 必调用 — single-user pop。

    严禁 cache.clear() 全清（会污染其他活跃用户的 cache）。
    """
    _TOKEN_VERSION_CACHE.pop(user_id, None)


def invalidate_all_token_version_cache() -> None:
    """v0.6.5.2 F4-back：全清 cache — 仅用于 rollout 全员 bump 这一全局事件。

    区别于 invalidate_token_version_cache 的 single-user pop（NRP-1）：rollout 时
    所有 user 的 token_version 都变了，clear() 全清是正确且安全的（无"污染他人"问题）。
    """
    _TOKEN_VERSION_CACHE.clear()


# ─── v0.6.5.2 F4-back：2FA rollout 一次性 session 失效 ──────────────────


def apply_rollout_session_invalidation() -> dict:
    """启动期幂等调用（main.py 模块级）— 2FA rollout 时一次性失效所有现存 session。

    R-2FA 不变量：「运维更新后全员重新登录，登录后再绑定」。机制 = bump 全员
    token_version → 旧 JWT 立即 401 JWT_REVOKED（deps.py:126）→ 前端 401 拦截器
    清 token + reload → Login。重登后 enrolled 走 verify / 未 enrolled 走 enroll。

    幂等 + 隔离：
    - TOTP-gated：KNOT_TOTP_REQUIRED != "true" → skip（与 deps.py gate 同条件）。
    - flag-gated：app_settings 标志已设 → skip（仅首次部署执行，不会每次重启踢人）。
    - 崩溃安全顺序：bump → set flag → clear cache（bump 先于 flag；中途崩溃则重启
      re-bump 仅多失效一次，绝不静默跳过 bump）。
    - 测试隔离（F4-1）：conftest 模块级 os.environ.setdefault("KNOT_TOTP_REQUIRED","false")
      使 import 时确定性走 totp_not_required 分支 skip（守护测试用 delenv 揭真默认）。
    """
    if os.getenv("KNOT_TOTP_REQUIRED", "true").strip().lower() != "true":
        return {"skipped": "totp_not_required"}

    from knot.repositories import settings_repo
    if settings_repo.get_app_setting(_ROLLOUT_FLAG_KEY):
        return {"skipped": "already_applied"}

    n = user_repo.bump_all_token_versions()
    settings_repo.set_app_setting(_ROLLOUT_FLAG_KEY, _utc_iso())
    invalidate_all_token_version_cache()
    return {"bumped": n}


# ─── enroll 流程（R-PB-B1-7 1 次码 + 强制 recovery codes 下载）─────────


def enroll_init(user_id: int) -> tuple[str, str]:
    """Step 1：生成 secret + otpauth:// URI（QR payload）— 不持久化。

    用户扫码后再调 enroll_complete 验证 + 持久化。
    """
    secret = pyotp.random_base32()  # 32 chars base32（160-bit）
    user = user_repo.get_user_by_id(user_id)
    username = user["username"] if user else f"user-{user_id}"
    qr_uri = pyotp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="KNOT",
    )
    return secret, qr_uri


def enroll_complete(
    user_id: int, secret: str, code: str,
) -> list[str]:
    """R-PB-B1-7：1 次动态码验证 + R-PB-B1-9 R-46-Tx 事务持久化。

    返 10 个明文 recovery codes（前端必须强制下载才能完成 enroll — UX 守护）。
    密文（bcrypt hash）在事务中写 totp_recovery_codes 表；明文仅本函数返一次。
    """
    # R-PB-B1-12：valid_window=1（容忍 enroll 时用户输入慢导致跨步长）
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return []  # 失败 — 调用方应返 400 + 不持久化（secret 失效）

    # 生成 10 个 recovery codes（明文返给用户；hash 落 DB）
    plain_codes = [_generate_recovery_code() for _ in range(_RECOVERY_CODE_COUNT)]
    code_hashes = [bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt()).decode("utf-8") for c in plain_codes]
    enrolled_at = _utc_iso()

    # R-PB-B1-9 R-46-Tx：secret + recovery_codes 同事务（任一失败全回滚）
    from knot.repositories.base import get_conn
    conn = get_conn()
    try:
        user_repo.set_totp_in_tx(conn, user_id, secret, enrolled_at)
        totp_repo.insert_recovery_codes_in_tx(conn, user_id, code_hashes)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return plain_codes


# ─── verify（R-PB-B1-12 valid_window=1 ±30s）──────────────────────────


def verify(user_id: int, code: str) -> bool:
    """login 后强制验证 — R-PB-B1-12 valid_window=1 容忍前后 1 个步长。

    rate_limit 5/min/user 由 api 层 Depends(rate_limit_totp_verify) 守护；
    本函数仅业务逻辑（验证 + last_used_at 更新；不做计数）。
    """
    user = user_repo.get_user_by_id(user_id)
    if not user or not user.get("totp_secret"):
        return False  # 未 enroll
    secret = user["totp_secret"]  # 已透明解密（_USER_ENCRYPTED_COLS 含 totp_secret）
    ok = pyotp.TOTP(secret).verify(code, valid_window=1)
    if ok:
        user_repo.set_totp_last_used_at(user_id, _utc_iso())
    return ok


# ─── consume_recovery（R-PB-B1-11 audit user.totp.recovery_code_used）─


def consume_recovery(user_id: int, code: str) -> bool:
    """单次使用 recovery code — bcrypt 比对 + mark_used。

    R-PB-B1-11：调用方（api/totp.py）成功后 INSERT audit_log
                action='user.totp.recovery_code_used'（高危事件）。
    """
    code = code.strip().upper()
    unused = totp_repo.get_unused_codes(user_id)
    for code_id, code_hash in unused:
        if bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8")):
            # WHERE used_at IS NULL 守护防 race 重复消费
            return totp_repo.mark_used_by_id(code_id)
    return False


# ─── reset（admin 重置 + R-PB-B1-13 bump token_version）───────────────


def reset(user_id: int) -> list[str]:
    """admin 重置 user TOTP — R-PB-B1-9 事务三合一：

    1. clear_totp（secret + enrolled_at + last_used_at NULL）
    2. delete_all_for_user（recovery_codes 全清）
    3. bump_token_version（旧 JWT 立即失效 — R-PB-B1-13）

    + 生成新 secret + 10 个 recovery codes（用户需重新 enroll；
      返的 codes 是占位 — 实际 enroll 后才会真正可用）。

    Caller (api/totp.py) 必须：
    - audit_log action='user.totp.reset'
    - cache invalidate（invalidate_token_version_cache(user_id)）
    """
    from knot.repositories.base import get_conn
    conn = get_conn()
    try:
        user_repo.clear_totp_in_tx(conn, user_id)
        totp_repo.delete_all_for_user_in_tx(conn, user_id)
        user_repo.bump_token_version_in_tx(conn, user_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    invalidate_token_version_cache(user_id)
    return []  # 重置只清空；新 secret 由用户重新 enroll 生成


def bump_token_version_only(user_id: int) -> int:
    """change_password 顺手调用（γ1 安全债清偿）— 单字段 +1 + cache invalidate。

    与 reset 不同：不清 TOTP；只让旧 JWT 失效。
    """
    # 守护者第 13 次 active 议题 1 — 与 enroll_complete / reset 一致 explicit rollback
    from knot.repositories.base import get_conn
    conn = get_conn()
    try:
        new_ver = user_repo.bump_token_version_in_tx(conn, user_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    invalidate_token_version_cache(user_id)
    return new_ver


# ─── helpers ──────────────────────────────────────────────────────────


def _generate_recovery_code() -> str:
    """10-char base32 大写 + 短横分隔（ABCDE-12345 风格 — 类比 GitHub）。"""
    import base64
    raw = secrets.token_bytes(_RECOVERY_CODE_BYTES)
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    # 取前 10 字符（_RECOVERY_CODE_BYTES=6 → b32 = 10 chars 去 padding 后）
    code = b32[:10].upper()
    return f"{code[:5]}-{code[5:]}"
