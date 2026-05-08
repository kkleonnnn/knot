"""bi_agent/core/crypto/fernet.py — Fernet 默认加密实现（v0.4.5）。

红线落点：
- R-34 master key 缺失 fail-fast（CryptoConfigError，严禁 silent fallback）
- R-35 加密产物必带 enc_v1: 前缀
- R-40 lru_cache 进程单例；测试 fixture cache_clear()
- R-42 Fernet key base64-urlsafe 32 字节校验 + 友好错误
- R-44 lru_cache 是线程安全的（CPython GIL + 内部锁），async 调用安全

Contract 3 边界：core 严禁 import models — 本模块定义本地 CryptoConfigError；
repositories catch 后翻译为 models.errors.ConfigMissingError。
"""
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "enc_v1:"
_ENV = "BIAGENT_MASTER_KEY"


class CryptoConfigError(Exception):
    """加密配置异常 — core 层本地（守 Contract 3 core-no-models）。

    repositories catch 后翻译为 bi_agent.models.errors.ConfigMissingError；
    services / api 层只见到 ConfigMissingError（领域异常树）。
    """


class FernetAdapter:
    """Fernet 实现 CryptoAdapter Protocol。"""

    def __init__(self, master_key: bytes):
        self._fernet = Fernet(master_key)

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            return ""
        if plaintext == "":
            return ENC_PREFIX  # 空串占位（区分 NULL）
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return ENC_PREFIX + token

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if not ciphertext.startswith(ENC_PREFIX):
            return ciphertext  # 老明文兼容（D5 INFO log 在 repos wrap 内打）
        body = ciphertext[len(ENC_PREFIX):]
        if body == "":
            return ""  # 空串占位反向
        try:
            return self._fernet.decrypt(body.encode("ascii")).decode("utf-8")
        except InvalidToken as e:
            raise CryptoConfigError(
                "解密失败 — master key 已变更或密文损坏"
            ) from e

    def is_encrypted(self, s: str) -> bool:
        return isinstance(s, str) and s.startswith(ENC_PREFIX)


@lru_cache(maxsize=1)
def get_crypto_adapter() -> FernetAdapter:
    """R-40 进程单例（lru_cache 线程安全 — CPython GIL + 内部锁，R-44 async 安全）。

    测试 fixture 必须主动调 get_crypto_adapter.cache_clear() 隔离。
    """
    raw = os.environ.get(_ENV)
    if not raw:
        raise CryptoConfigError(f"{_ENV} 未设置 — v0.4.5 必须配置主密钥")
    try:
        key_bytes = raw.encode() if isinstance(raw, str) else raw
        return FernetAdapter(key_bytes)
    except (ValueError, TypeError) as e:
        raise CryptoConfigError(
            f"{_ENV} 格式无效（需 Fernet base64-urlsafe 32 字节）: {e}"
        ) from e


def assert_master_key_loaded() -> None:
    """启动期主动校验 — main.py 在 init_db() 之后调用（R-45）。"""
    get_crypto_adapter()
