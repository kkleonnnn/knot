"""settings_repo — app_settings KV + model_settings + agent model config。"""
from __future__ import annotations

import json

from bi_agent.repositories.base import get_conn

# ── 通用 KV ────────────────────────────────────────────────────────────

def get_app_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_app_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now','localtime')",
        (key, value, value),
    )
    conn.commit()
    conn.close()


# ── model_settings 表 ──────────────────────────────────────────────────

def get_model_settings() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM model_settings").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_model_enabled(model_key: str, enabled: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO model_settings (model_key, enabled) VALUES (?,?) "
        "ON CONFLICT(model_key) DO UPDATE SET enabled=?, updated_at=datetime('now','localtime')",
        (model_key, enabled, enabled),
    )
    conn.commit()
    conn.close()


def set_default_model(model_key: str):
    conn = get_conn()
    conn.execute("UPDATE model_settings SET is_default=0")
    conn.execute(
        "INSERT INTO model_settings (model_key, enabled, is_default) VALUES (?,1,1) "
        "ON CONFLICT(model_key) DO UPDATE SET is_default=1, updated_at=datetime('now','localtime')",
        (model_key,),
    )
    conn.commit()
    conn.close()


# ── 全局 agent 模型映射（存 app_settings.key='agent_model_config'）──────

def get_agent_model_config() -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key='agent_model_config'"
    ).fetchone()
    conn.close()
    if row and row["value"]:
        try:
            return json.loads(row["value"])
        except Exception:
            pass
    return {}


def set_agent_model_config(config: dict):
    v = json.dumps(config, ensure_ascii=False)
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('agent_model_config', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now','localtime')",
        (v, v),
    )
    conn.commit()
    conn.close()
