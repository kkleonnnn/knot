"""tests/scripts/test_migrate_encrypt_v045.py — v0.4.5 commit #3 守护测试（TDD）。

覆盖：
- R-36 幂等：见 enc_v1: 跳过；多次运行结果一致
- R-41 独立 entrypoint：grep main.py / base.py 零命中
- R-46 自动 bak（dry-run 不创建；timestamp 后缀避免覆盖；master key 缺失先 fail）
- R-46-Tx 每表单事务（中断单表回滚；其他表不受影响）
- dry-run 0 副作用（DB SHA256 一致）
"""
import hashlib
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from bi_agent.core.crypto import ENC_PREFIX, encrypt
from bi_agent.core.crypto.fernet import get_crypto_adapter
from bi_agent.repositories import data_source_repo, settings_repo, user_repo


def _db_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _seed_legacy_plaintext(db_path: str):
    """模拟 v0.4.4 老 DB：直接走 sqlite3 写明文，绕过 repo 加密 wrap。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, api_key, "
        "openrouter_api_key, embedding_api_key, doris_password) "
        "VALUES ('legacy1', 'h', 'analyst', 'sk-old', 'or-old', 'em-old', 'doris-old')"
    )
    conn.execute(
        "INSERT INTO data_sources (user_id, name, db_host, db_port, db_user, db_password, db_database) "
        "VALUES (NULL, 'ds-legacy', 'h', 9030, 'u', 'ds-old-pw', 'db')"
    )
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('openrouter_api_key', 'global-or-plain')"
    )
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('default_model', 'claude-haiku')"
    )
    conn.commit()
    conn.close()


# ─── R-36 幂等 ─────────────────────────────────────────────────────────

def test_migrate_encrypts_all_targets(tmp_db_path):
    """全 6 列覆盖 — 老明文跑迁移后全部带 enc_v1: 前缀。"""
    _seed_legacy_plaintext(tmp_db_path)
    from bi_agent.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=False)
    assert stats["scanned"] >= 3  # 至少 1 user + 1 ds + 1 sensitive setting
    assert stats["encrypted"] >= 3

    conn = sqlite3.connect(tmp_db_path)
    for col in ("api_key", "openrouter_api_key", "embedding_api_key", "doris_password"):
        v = conn.execute(f"SELECT {col} FROM users WHERE username='legacy1'").fetchone()[0]
        assert v.startswith(ENC_PREFIX), f"users.{col} 应已加密"
    ds_pw = conn.execute("SELECT db_password FROM data_sources WHERE name='ds-legacy'").fetchone()[0]
    assert ds_pw.startswith(ENC_PREFIX)
    or_v = conn.execute("SELECT value FROM app_settings WHERE key='openrouter_api_key'").fetchone()[0]
    assert or_v.startswith(ENC_PREFIX)
    # 非白名单 default_model 不应加密
    dm = conn.execute("SELECT value FROM app_settings WHERE key='default_model'").fetchone()[0]
    assert not dm.startswith(ENC_PREFIX)
    conn.close()


def test_R36_migrate_idempotent_run_twice_noop(tmp_db_path):
    """R-36：跑两次第二次 encrypted=0；DB content 不变（防"看似 noop 实际重新加密"）。"""
    _seed_legacy_plaintext(tmp_db_path)
    from bi_agent.scripts import migrate_encrypt_v045
    migrate_encrypt_v045.migrate(dry_run=False)
    sha_after_first = _db_sha256(tmp_db_path)

    stats2 = migrate_encrypt_v045.migrate(dry_run=False)
    assert stats2["encrypted"] == 0, "R-36：第二次跑应零加密"
    sha_after_second = _db_sha256(tmp_db_path)
    assert sha_after_first == sha_after_second, "R-36：DB content 不应变（无重复加密）"


def test_migrate_skips_already_encrypted_row(tmp_db_path):
    """混合行：已加密 + 老明文同时存在，迁移只动老明文。"""
    user_repo.create_user("new", "h", "N", "analyst", "h", 9030, "u", "fresh-pw", "db")  # 已加密
    _seed_legacy_plaintext(tmp_db_path)  # 老明文

    from bi_agent.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=False)

    # legacy1 老明文应被加密；new 用户的 fresh-pw 已加密 → skipped
    assert stats["encrypted"] >= 3
    # 验证 new 用户 doris_password 通过 repo 解密仍是 fresh-pw（未被二次加密）
    new_user = user_repo.get_user_by_username("new")
    assert new_user["doris_password"] == "fresh-pw"


# ─── dry-run 0 副作用 ────────────────────────────────────────────────

def test_migrate_dry_run_does_not_write(tmp_db_path):
    _seed_legacy_plaintext(tmp_db_path)
    sha_before = _db_sha256(tmp_db_path)

    from bi_agent.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=True)

    sha_after = _db_sha256(tmp_db_path)
    assert sha_before == sha_after, "dry-run DB 不应被写"
    # dry-run 应统计 would_encrypt 数量
    assert stats["encrypted"] >= 3, "dry-run 仍应统计 would_encrypt 数"

    # 守护者提示：dry-run 不创建 bak
    db_dir = Path(tmp_db_path).parent
    bak_files = list(db_dir.glob(f"{Path(tmp_db_path).name}*.bak"))
    assert not bak_files, "dry-run 严禁创建 .bak"


# ─── R-46 自动备份 ───────────────────────────────────────────────────

def test_R46_migrate_creates_backup_before_write(tmp_db_path):
    """R-46：写第一个 UPDATE 之前生成 bak；内容 = 原 db。"""
    _seed_legacy_plaintext(tmp_db_path)
    sha_orig = _db_sha256(tmp_db_path)

    from bi_agent.scripts import migrate_encrypt_v045
    bak_path = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]

    assert bak_path is not None
    assert Path(bak_path).exists(), "bak 必须生成"
    assert _db_sha256(bak_path) == sha_orig, "bak 内容必须 = 原 db（未被改写）"
    assert ".v044" in bak_path, "bak 命名带版本号便于回溯"


def test_R46_bak_timestamped_does_not_overwrite_previous(tmp_db_path):
    """守护者提示：多次跑应用 timestamp 后缀，不覆盖前一次 bak（数据丢失教训）。"""
    _seed_legacy_plaintext(tmp_db_path)

    from bi_agent.scripts import migrate_encrypt_v045
    bak1 = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]
    # 故意改 DB 模拟"第一次 bak 后又有变更"
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('post1', 'h', 'analyst')")
    conn.commit()
    conn.close()
    # 解开"已加密"使第二次跑还有事可做（确实有新明文）— 通过新加用户绕开 already-encrypted 跳过
    _seed_legacy_plaintext_more(tmp_db_path)

    bak2 = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]

    assert bak1 != bak2, "两次 bak 路径必须不同（timestamp 后缀）"
    assert Path(bak1).exists() and Path(bak2).exists(), "两个 bak 都应保留"


def _seed_legacy_plaintext_more(db_path: str):
    """补一些老明文，确保第二次迁移有事可做。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, api_key) "
        "VALUES ('legacy2', 'h', 'analyst', 'sk-second-batch')"
    )
    conn.commit()
    conn.close()


# ─── R-46-Tx 每表单事务 ──────────────────────────────────────────────

def test_R46_Tx_per_table_transaction_rollback_on_error(tmp_db_path, monkeypatch):
    """R-46-Tx：mock encrypt 在处理 data_sources 时抛 ValueError →
    data_sources 全表回滚；users 表（已先处理）应保持加密；app_settings（之后）应跳过。"""
    _seed_legacy_plaintext(tmp_db_path)

    from bi_agent.scripts import migrate_encrypt_v045

    call_count = {"n": 0}
    real_encrypt = migrate_encrypt_v045.encrypt

    def _flaky_encrypt(s):
        call_count["n"] += 1
        # users 4 列已加密后；进入 data_sources 抛错
        if "ds-old-pw" in s:
            raise ValueError("simulated mid-table failure")
        return real_encrypt(s)

    monkeypatch.setattr(migrate_encrypt_v045, "encrypt", _flaky_encrypt)

    with pytest.raises(ValueError):
        migrate_encrypt_v045.migrate(dry_run=False)

    conn = sqlite3.connect(tmp_db_path)
    # users 表已 commit → 应已加密
    api = conn.execute("SELECT api_key FROM users WHERE username='legacy1'").fetchone()[0]
    assert api.startswith(ENC_PREFIX), "users 表先处理且已 commit，应保持加密"
    # data_sources 表 rollback → 仍是明文
    ds_pw = conn.execute("SELECT db_password FROM data_sources WHERE name='ds-legacy'").fetchone()[0]
    assert ds_pw == "ds-old-pw", "data_sources 表中失败应整表回滚"
    conn.close()


# ─── R-41 独立 entrypoint ────────────────────────────────────────────

def test_R41_migrate_not_called_in_main_or_base():
    """R-41：grep 守护 — main.py / base.py 不得引用 migrate_encrypt。"""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "migrate_encrypt", "bi_agent/main.py", "bi_agent/repositories/base.py"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"R-41：startup hook 不应引用 migrate；命中：{result.stdout}"


# ─── 守护者提示：master key 缺失先 fail，不创建 bak ───────────────────

def test_R46_no_master_key_fails_before_backup(tmp_db_path, monkeypatch):
    """守护者提示：master key 缺失立即 fail，不创建 bak（避免浪费磁盘 / 误导）。"""
    monkeypatch.delenv("BIAGENT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()

    from bi_agent.core.crypto.fernet import CryptoConfigError
    from bi_agent.scripts import migrate_encrypt_v045
    with pytest.raises(CryptoConfigError):
        migrate_encrypt_v045.migrate(dry_run=False)

    # 关键：不应创建 bak
    db_dir = Path(tmp_db_path).parent
    bak_files = list(db_dir.glob(f"{Path(tmp_db_path).name}*.bak"))
    assert not bak_files, "master key 缺失时严禁先创建 bak"
