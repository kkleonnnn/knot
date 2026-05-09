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

_USER_ENCRYPTED_COLS = ("api_key", "openrouter_api_key", "embedding_api_key", "doris_password")


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
