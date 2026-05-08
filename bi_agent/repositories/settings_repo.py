"""settings_repo — app_settings KV + model_settings + agent model config。

v0.4.5：sensitive key 白名单透明加解密（守 R-38 / R-43 / R-43-Dual）。
"""
from __future__ import annotations

import json

from bi_agent.core.crypto import decrypt, encrypt, is_encrypted
from bi_agent.core.crypto.fernet import CryptoConfigError
from bi_agent.core.logging_setup import logger
from bi_agent.models.errors import ConfigMissingError
from bi_agent.repositories.base import get_conn

# 敏感 setting key 白名单 — 新增 sensitive setting 必须更新此集合（CLAUDE.md 流程红线）
_SENSITIVE_KEYS = frozenset({"openrouter_api_key", "embedding_api_key"})


# ── 通用 KV ────────────────────────────────────────────────────────────

def get_app_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    raw = row["value"]
    # 白名单 → 必解密
    if key in _SENSITIVE_KEYS:
        if not raw:
            return default
        try:
            return decrypt(raw)
        except CryptoConfigError as e:
            raise ConfigMissingError(str(e)) from e
    # R-43 失败安全：非白名单但内容带 enc_v1: 前缀 → 也尝试解密（防漏配置）
    if raw and is_encrypted(raw):
        try:
            return decrypt(raw)
        except CryptoConfigError:
            return raw  # 解密失败回退原值（避免老明文 + key 切换误伤）
    return raw if raw else default


def set_app_setting(key: str, value: str):
    if key in _SENSITIVE_KEYS:
        value = encrypt(value or "")
    elif value and is_encrypted(value):
        # R-43-Dual：写非白名单 key 时若值已 enc_v1: 格式 → 跳过二次加密 + WARNING
        logger.warning(
            f"set_app_setting({key}=...): 值已带 {is_encrypted.__name__} 前缀，跳过二次加密"
        )
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
