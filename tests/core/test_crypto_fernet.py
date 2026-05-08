"""tests/core/test_crypto_fernet.py — v0.4.5 commit #1 守护测试（TDD 先行）。

覆盖：
- R-34 master key 缺失 fail-fast
- R-35 加密产物必带 enc_v1: 前缀
- R-37 conftest fixture 隔离（top-level conftest.py）
- R-40 lru_cache 单例 + cache_clear 验证
- R-42 Fernet key 格式校验 + 友好错误
- R-44 lru_cache 已线程安全（docstring 显式记录）
"""
import pytest

from bi_agent.core.crypto import decrypt, encrypt, is_encrypted
from bi_agent.core.crypto.fernet import (
    ENC_PREFIX,
    CryptoConfigError,
    assert_master_key_loaded,
    get_crypto_adapter,
)


def test_encrypt_decrypt_roundtrip():
    """任意 utf-8 字符串往返一致。"""
    samples = ["hello", "中文密码", "sk-ant-api03-xxxxx", "with spaces and symbols !@#$%"]
    for s in samples:
        assert decrypt(encrypt(s)) == s


def test_encrypt_produces_enc_v1_prefix():
    """R-35：加密产物必带 enc_v1: 前缀。"""
    out = encrypt("plain")
    assert out.startswith(ENC_PREFIX)
    assert is_encrypted(out)


def test_encrypt_same_plaintext_different_ciphertext():
    """Fernet 自带随机 IV → 同明文两次加密产物不同。"""
    a = encrypt("same")
    b = encrypt("same")
    assert a != b
    assert decrypt(a) == decrypt(b) == "same"


def test_master_key_missing_raises_config_missing_error(monkeypatch):
    """R-34：BIAGENT_MASTER_KEY 缺失 → CryptoConfigError。"""
    monkeypatch.delenv("BIAGENT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError, match="未设置"):
        assert_master_key_loaded()


def test_master_key_invalid_format_raises(monkeypatch):
    """R-42：非 base64-urlsafe 32 字节 → 友好错误（非裸 ValueError）。"""
    monkeypatch.setenv("BIAGENT_MASTER_KEY", "not-a-valid-fernet-key")
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError, match="格式无效"):
        assert_master_key_loaded()


def test_decrypt_no_prefix_returns_as_is():
    """老明文兼容：见无前缀直接返回（迁移期 D5 INFO 日志在 repos wrap 内打）。"""
    legacy = "sk-ant-legacy-plaintext"
    assert decrypt(legacy) == legacy


def test_decrypt_wrong_key_raises_crypto_config_error(monkeypatch):
    """R-42 边界：密文用 keyA 加，换 keyB 解 → CryptoConfigError 翻译。"""
    ct = encrypt("secret")
    # 切换到另一个 key
    new_key = "RbU1qJOKDpyRpaeQEvO7G0YkU9tnxAjLfqg0gQNFLjI="  # 另一个有效 Fernet key
    monkeypatch.setenv("BIAGENT_MASTER_KEY", new_key)
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError, match="解密失败"):
        decrypt(ct)


def test_empty_string_roundtrip():
    """空串占位语义：encrypt('') = enc_v1: ；decrypt('enc_v1:') = ''。"""
    out = encrypt("")
    assert out == ENC_PREFIX
    assert decrypt(out) == ""
    assert decrypt("") == ""
    assert decrypt(None) == ""


def test_lru_cache_single_instance_per_process():
    """R-40：同一 key 下 get_crypto_adapter 返回同一实例（lru_cache）。"""
    a1 = get_crypto_adapter()
    a2 = get_crypto_adapter()
    assert a1 is a2


def test_cache_clear_resets_instance(monkeypatch):
    """R-40：cache_clear() 后下次拿到的是新实例（fixture 用此机制隔离）。"""
    a1 = get_crypto_adapter()
    get_crypto_adapter.cache_clear()
    a2 = get_crypto_adapter()
    assert a1 is not a2  # 清缓存后是新实例
