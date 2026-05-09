"""knot/core/crypto/base.py — CryptoAdapter Protocol（v0.4.5 R-38）。

加密器协议；core 层横切工具，repositories / scripts 可反向 import；
api / services / adapters / models 严禁 import（守 7th contract
crypto-only-in-allowed-callers）。
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class CryptoAdapter(Protocol):
    """字段级加解密协议。"""

    def encrypt(self, plaintext: str) -> str:
        """明文 → enc_v1: 前缀 + Fernet token。空串/None 处理见实现。"""
        ...

    def decrypt(self, ciphertext: str) -> str:
        """密文 → 明文；无前缀视为老明文兼容回传；空串/None → 空串。"""
        ...

    def is_encrypted(self, s: str) -> bool:
        """前缀检查（迁移幂等用）。"""
        ...
