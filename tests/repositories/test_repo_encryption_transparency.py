"""tests/repositories/test_repo_encryption_transparency.py — v0.4.5 commit #2 守护测试。

覆盖：
- R-38 加解密只在 core/crypto + repositories（透明，调用方零改动）
- R-43 settings_repo 失败安全：未知 key 但 enc_v1: 前缀 → 必须解密
- R-43-Dual 写入对偶：未知 key 已 enc_v1: 格式 → 跳过二次加密 + WARNING

边界翻译：repos catch core CryptoConfigError → 抛 models.ConfigMissingError。
"""
import sqlite3

import pytest

from knot.core.crypto import ENC_PREFIX, encrypt
from knot.core.crypto.fernet import get_crypto_adapter
from knot.models.errors import ConfigMissingError
from knot.repositories import data_source_repo, settings_repo, user_repo
from knot.repositories.base import get_conn


def _raw_value(table: str, col: str, where_sql: str, params: tuple):
    """直接走 sqlite3 读 raw value，绕开 repo 层 — 验证 at-rest 状态。"""
    conn = get_conn()
    row = conn.execute(f"SELECT {col} FROM {table} WHERE {where_sql}", params).fetchone()
    conn.close()
    return row[col] if row else None


# ─── R-38 透明加解密 ────────────────────────────────────────────────────

def test_create_user_doris_password_encrypted_at_rest(tmp_db_path):
    user_repo.create_user(
        "alice", "hash", "Alice", "analyst",
        "h", 9030, "u", "secret-doris-pw", "db",
    )
    raw = _raw_value("users", "doris_password", "username=?", ("alice",))
    assert raw.startswith(ENC_PREFIX), "DB at-rest 应见 enc_v1: 密文"
    user = user_repo.get_user_by_username("alice")
    assert user["doris_password"] == "secret-doris-pw", "调用方拿明文（透明）"


def test_get_user_returns_decrypted_api_key(tmp_db_path):
    user_repo.create_user("bob", "h", "B", "analyst", "h", 9030, "u", "p", "db")
    uid = user_repo.get_user_by_username("bob")["id"]
    user_repo.update_user(uid, api_key="sk-ant-real-key-123")
    user = user_repo.get_user_by_id(uid)
    assert user["api_key"] == "sk-ant-real-key-123"


def test_update_user_api_key_writes_encrypted(tmp_db_path):
    user_repo.create_user("c", "h", "C", "analyst", "h", 9030, "u", "p", "db")
    uid = user_repo.get_user_by_username("c")["id"]
    user_repo.update_user(uid, api_key="sk-test", openrouter_api_key="or-test")
    raw_api = _raw_value("users", "api_key", "id=?", (uid,))
    raw_or = _raw_value("users", "openrouter_api_key", "id=?", (uid,))
    assert raw_api.startswith(ENC_PREFIX)
    assert raw_or.startswith(ENC_PREFIX)


def test_list_users_decrypts_all_rows(tmp_db_path):
    user_repo.create_user("d1", "h", "D1", "analyst", "h", 9030, "u", "pw1", "db")
    user_repo.create_user("d2", "h", "D2", "analyst", "h", 9030, "u", "pw2", "db")
    rows = user_repo.list_users()
    pws = sorted(r["doris_password"] for r in rows if r["username"].startswith("d"))
    assert pws == ["pw1", "pw2"], "list_users 应解密所有行"


def test_data_source_db_password_encrypted(tmp_db_path):
    sid = data_source_repo.create_datasource(
        user_id=None, name="ds1", description="x",
        db_host="h", db_port=9030, db_user="u", db_password="ds-secret",
        db_database="db",
    )
    raw = _raw_value("data_sources", "db_password", "id=?", (sid,))
    assert raw.startswith(ENC_PREFIX)
    ds = data_source_repo.get_datasource(sid)
    assert ds["db_password"] == "ds-secret"


def test_data_source_update_password_encrypted(tmp_db_path):
    sid = data_source_repo.create_datasource(
        user_id=None, name="ds2", description="x",
        db_host="h", db_port=9030, db_user="u", db_password="initial",
        db_database="db",
    )
    data_source_repo.update_datasource(sid, db_password="rotated")
    raw = _raw_value("data_sources", "db_password", "id=?", (sid,))
    assert raw.startswith(ENC_PREFIX)
    assert data_source_repo.get_datasource(sid)["db_password"] == "rotated"


def test_app_setting_openrouter_api_key_encrypted(tmp_db_path):
    settings_repo.set_app_setting("openrouter_api_key", "or-key-real")
    raw = _raw_value("app_settings", "value", "key=?", ("openrouter_api_key",))
    assert raw.startswith(ENC_PREFIX)
    assert settings_repo.get_app_setting("openrouter_api_key") == "or-key-real"


def test_app_setting_non_sensitive_key_plaintext(tmp_db_path):
    """白名单外的 key（如 default_model）应保持明文存储。"""
    settings_repo.set_app_setting("default_model", "claude-haiku-4-5-20251001")
    raw = _raw_value("app_settings", "value", "key=?", ("default_model",))
    assert not raw.startswith(ENC_PREFIX), "非白名单不应加密"
    assert settings_repo.get_app_setting("default_model") == "claude-haiku-4-5-20251001"


# ─── 老明文兼容（D5 INFO log） ─────────────────────────────────────────

def test_legacy_plaintext_row_decrypts_as_passthrough(tmp_db_path):
    """老 v0.4.4 数据：DB 直接写明文（绕 repo），repo 读取应透传不报错。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (username, password_hash, doris_password, role) "
        "VALUES ('legacy', 'h', 'old-plaintext-pw', 'analyst')"
    )
    conn.commit()
    conn.close()
    user = user_repo.get_user_by_username("legacy")
    assert user["doris_password"] == "old-plaintext-pw"


# ─── R-43 settings_repo 失败安全 ───────────────────────────────────────

def test_R43_failsafe_unknown_key_with_enc_prefix_decrypts(tmp_db_path):
    """未知 key 但内容带 enc_v1: 前缀 → 必须尝试解密（防漏配置 sensitive 名单）。"""
    settings_repo.set_app_setting("ad_hoc_secret", encrypt("smuggled"))
    # ad_hoc_secret 不在 _SENSITIVE_KEYS，但值已是 enc_v1:
    val = settings_repo.get_app_setting("ad_hoc_secret")
    assert val == "smuggled", "R-43：见 enc_v1: 前缀必须解密回明文"


def test_R43_dual_write_skips_double_encrypt_on_already_encrypted(tmp_db_path, caplog):
    """R-43-Dual：写非白名单 key 时若值已 enc_v1: 格式 → 跳过二次加密 + WARNING。"""
    import logging
    caplog.set_level(logging.WARNING)
    pre_enc = encrypt("origin")
    settings_repo.set_app_setting("ad_hoc_2", pre_enc)  # 误传已加密值
    raw = _raw_value("app_settings", "value", "key=?", ("ad_hoc_2",))
    # 不应出现 enc_v1:enc_v1:... 双重加密
    assert raw == pre_enc, "R-43-Dual：值应原样存（无二次加密）"
    # 取回时见 enc_v1: 走解密 → 拿到原明文
    assert settings_repo.get_app_setting("ad_hoc_2") == "origin"


# ─── 边界翻译：core CryptoConfigError → models ConfigMissingError ──────

def test_repo_translates_crypto_config_error_to_config_missing(tmp_db_path, monkeypatch):
    """换 master key 后历史密文解不开 → repo 应翻译为 ConfigMissingError（领域异常树）。"""
    user_repo.create_user("e", "h", "E", "analyst", "h", 9030, "u", "secret", "db")
    # 切到不同 master key
    other_key = "RbU1qJOKDpyRpaeQEvO7G0YkU9tnxAjLfqg0gQNFLjI="
    monkeypatch.setenv("BIAGENT_MASTER_KEY", other_key)
    monkeypatch.delenv("KNOT_MASTER_KEY", raising=False)  # v0.5.0 R-68：测旧 KEY 切换
    get_crypto_adapter.cache_clear()
    with pytest.raises(ConfigMissingError, match="解密失败"):
        user_repo.get_user_by_username("e")
