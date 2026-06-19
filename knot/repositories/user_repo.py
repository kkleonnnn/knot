"""user_repo — users 表 CRUD + 用量统计。

v0.4.5：4 个敏感列（api_key / openrouter_api_key / embedding_api_key / doris_password）
透明加解密 — 写时 encrypt / 读时 decrypt（守 R-38）。
core CryptoConfigError → models ConfigMissingError 边界翻译。
"""
from __future__ import annotations

import json
import sqlite3

from knot.core.crypto import decrypt, encrypt
from knot.core.crypto.fernet import CryptoConfigError
from knot.models.errors import ConfigMissingError
from knot.repositories.base import get_conn

_USER_ENCRYPTED_COLS = (
    "api_key", "openrouter_api_key", "embedding_api_key", "doris_password",
    # v0.6.2.0 TOTP 2FA — R-PB-B1-1/8 Fernet enc_v1: 前缀
    "totp_secret",
)


def _decrypt_user_row(row) -> dict | None:
    """透明 wrap：把 row 中所有敏感列解密；CryptoConfigError 翻译为 ConfigMissingError。"""
    if row is None:
        return None
    out = dict(row)
    for col in _USER_ENCRYPTED_COLS:
        if col in out and out[col]:
            try:
                out[col] = decrypt(out[col])
            except CryptoConfigError as e:
                raise ConfigMissingError(str(e)) from e
    return out


def get_user_by_username(username: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return _decrypt_user_row(row)


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return _decrypt_user_row(row)


def list_users() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [_decrypt_user_row(r) for r in rows]


def create_user(username, password_hash, display_name, role,
                doris_host, doris_port, doris_user, doris_password, doris_database) -> bool:
    enc_doris_pw = encrypt(doris_password) if doris_password else doris_password
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO users "
            "(username, password_hash, display_name, role, doris_host, doris_port, doris_user, doris_password, doris_database) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (username, password_hash, display_name, role,
             doris_host, doris_port, doris_user, enc_doris_pw, doris_database),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    # 敏感列写时 encrypt（None / 空值不动）
    for col in _USER_ENCRYPTED_COLS:
        if col in kwargs and kwargs[col]:
            kwargs[col] = encrypt(kwargs[col])
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    conn = get_conn()
    conn.execute(f"UPDATE users SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()


def update_user_usage(user_id: int, input_tokens: int, output_tokens: int,
                      cost_usd: float, query_time_ms: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET "
        "monthly_tokens = monthly_tokens + ?, "
        "monthly_cost_usd = monthly_cost_usd + ?, "
        "query_count = query_count + 1, "
        "avg_response_ms = CAST((avg_response_ms * query_count + ?) / (query_count + 1) AS INTEGER) "
        "WHERE id=?",
        (input_tokens + output_tokens, cost_usd, query_time_ms, user_id),
    )
    conn.commit()
    conn.close()


def get_user_monthly_usage(user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT monthly_tokens, monthly_cost_usd, avg_response_ms, query_count FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_monthly_cost() -> float:
    conn = get_conn()
    row = conn.execute("SELECT SUM(monthly_cost_usd) AS total FROM users").fetchone()
    conn.close()
    return row["total"] or 0.0


# Per-user agent model config（JSON 字段，存在 users.agent_model_config 列）

def get_user_agent_model_config(user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT agent_model_config FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if row and row["agent_model_config"]:
        try:
            return json.loads(row["agent_model_config"])
        except Exception:
            pass
    return {}


def set_user_agent_model_config(user_id: int, config: dict):
    v = json.dumps(config, ensure_ascii=False)
    conn = get_conn()
    conn.execute("UPDATE users SET agent_model_config=? WHERE id=?", (v, user_id))
    conn.commit()
    conn.close()


# ─── v0.6.2.0 TOTP 2FA support ─────────────────────────────────────────
# R-PB-B1-9 R-46-Tx：set/clear 走传入 conn 实现 secret + recovery_codes 同事务
# R-PB-B1-13：bump_token_version 触发 reset / change_password 时旧 JWT 立即失效


def set_totp_in_tx(conn: sqlite3.Connection, user_id: int,
                   secret_plain: str, enrolled_at: str) -> None:
    """R-PB-B1-9 R-46-Tx：在传入 conn 事务中写 totp_secret + enrolled_at。

    secret 经 Fernet 加密 enc_v1: 前缀（R-PB-B1-1/8）；不 commit / 不 close，
    由调用方（totp_service.enroll_complete）统一 commit 或 rollback。
    """
    enc_secret = encrypt(secret_plain)
    conn.execute(
        "UPDATE users SET totp_secret=?, totp_enrolled_at=? WHERE id=?",
        (enc_secret, enrolled_at, user_id),
    )


def clear_totp_in_tx(conn: sqlite3.Connection, user_id: int) -> None:
    """R-PB-B1-9：reset 时事务中清除 secret + enrolled_at + last_used_at。

    配合 totp_repo.delete_all_for_user_in_tx + bump_token_version 三步同事务，
    保证 admin 重置 → 用户旧 JWT 立即失效 + 必须重新 enroll。
    """
    conn.execute(
        "UPDATE users SET totp_secret=NULL, totp_enrolled_at=NULL, "
        "totp_last_used_at=NULL WHERE id=?",
        (user_id,),
    )


def set_totp_last_used_at(user_id: int, dt_str: str) -> None:
    """verify 成功时调用 — 独立 commit（不需事务保证）。

    R-PB-B1-5 月 ≥5 次警报基线：last_used_at 用于审计聚合。
    """
    conn = get_conn()
    conn.execute(
        "UPDATE users SET totp_last_used_at=? WHERE id=?", (dt_str, user_id),
    )
    conn.commit()
    conn.close()


def get_token_version(user_id: int) -> int:
    """R-PB-B1-13：JWT 验证读 users.token_version；不匹配 → 401 JWT_REVOKED。

    Service 层 totp_service.get_token_version_cached 包一层 cachetools TTLCache。
    本函数永远走 DB（cache miss / invalidate 后调用）。
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT token_version FROM users WHERE id=?", (user_id,),
    ).fetchone()
    conn.close()
    return int(row["token_version"]) if row else 0


def bump_token_version_in_tx(conn: sqlite3.Connection, user_id: int) -> int:
    """R-PB-B1-13：reset / change_password 触发 +1 → 旧 JWT 立即失效。

    返回新版本号；调用方负责 cache invalidate（totp_service.invalidate_token_version_cache）。
    传入 conn 模式 — 与 set/clear_totp 同事务。
    """
    conn.execute(
        "UPDATE users SET token_version = token_version + 1 WHERE id=?",
        (user_id,),
    )
    row = conn.execute(
        "SELECT token_version FROM users WHERE id=?", (user_id,),
    ).fetchone()
    return int(row["token_version"]) if row else 0


def bump_all_token_versions() -> int:
    """v0.6.5.2 F4-back：全表 token_version +1（无 WHERE）→ 失效所有现存 JWT。

    用于 2FA rollout 一次性 session 失效（运维更新后全员重登）。
    返回受影响行数。调用方（totp_service.apply_rollout_session_invalidation）负责
    设 app_settings 一次性标志 + 全清 token_version cache。
    """
    conn = get_conn()
    try:
        cur = conn.execute("UPDATE users SET token_version = token_version + 1")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
