"""user_repo — users 表 CRUD + 用量统计。"""
from __future__ import annotations

import json
import sqlite3

from bi_agent.repositories.base import get_conn


def get_user_by_username(username: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username, password_hash, display_name, role,
                doris_host, doris_port, doris_user, doris_password, doris_database) -> bool:
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO users "
            "(username, password_hash, display_name, role, doris_host, doris_port, doris_user, doris_password, doris_database) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (username, password_hash, display_name, role,
             doris_host, doris_port, doris_user, doris_password, doris_database),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
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
