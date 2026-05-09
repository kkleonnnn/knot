"""knot/core/crypto — 字段级加密横切工具（v0.4.5）。

仅 repositories / scripts 可 import（守 7th contract crypto-only-in-allowed-callers）。
api / services / adapters / models 见到的全部是明文（透明加解密）。

便捷顶层函数（一行 import）：
    from knot.core.crypto import encrypt, decrypt, is_encrypted
"""
from knot.core.crypto.base import CryptoAdapter
from knot.core.crypto.fernet import (
    ENC_PREFIX,
    CryptoConfigError,
    FernetAdapter,
    assert_master_key_loaded,
    get_crypto_adapter,
)


def encrypt(plaintext: str) -> str:
    return get_crypto_adapter().encrypt(plaintext)


def decrypt(ciphertext: str) -> str:
    return get_crypto_adapter().decrypt(ciphertext)


def is_encrypted(s: str) -> bool:
    return get_crypto_adapter().is_encrypted(s)


__all__ = [
    "CryptoAdapter",
    "CryptoConfigError",
    "ENC_PREFIX",
    "FernetAdapter",
    "assert_master_key_loaded",
    "decrypt",
    "encrypt",
    "get_crypto_adapter",
    "is_encrypted",
]
