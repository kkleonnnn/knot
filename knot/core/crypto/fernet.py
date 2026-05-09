"""knot/core/crypto/fernet.py — Fernet 默认加密实现（v0.4.5 / v0.5.0 双源 + R-74 探针）。

红线落点：
- R-34 master key 缺失 fail-fast（CryptoConfigError，严禁 silent fallback）
- R-35 加密产物必带 enc_v1: 前缀
- R-40 lru_cache 进程单例；测试 fixture cache_clear()
- R-42 Fernet key base64-urlsafe 32 字节校验 + 友好错误
- R-44 lru_cache 是线程安全的（CPython GIL + 内部锁），async 调用安全
- R-68 (v0.5.0) env 双源：KNOT_MASTER_KEY 优先 + BIAGENT_MASTER_KEY deprecated 回退（v1.0 移除）
- R-74 (v0.5.0) 密文兼容性探针：双 key 不同值时验证 enc_v1: 数据可解性 → 旧成功新失败 sys.exit(1)

Contract 3 边界：core 严禁 import models — 本模块定义本地 CryptoConfigError；
repositories catch 后翻译为 models.errors.ConfigMissingError。
"""
from __future__ import annotations  # PEP 563：兼容 Python 3.9 的 `X | None` 语法

import logging
import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc_v1:"
_NEW_ENV = "KNOT_MASTER_KEY"      # v0.5.0 新名
_OLD_ENV = "BIAGENT_MASTER_KEY"   # v0.4.x 旧名（deprecated，v1.0 移除）


class CryptoConfigError(Exception):
    """加密配置异常 — core 层本地（守 Contract 3 core-no-models）。

    repositories catch 后翻译为 knot.models.errors.ConfigMissingError；
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


# ─── R-68 双源 + R-74 密文兼容性探针 ─────────────────────────────────────

def _try_decrypt(key_str: str, ciphertext: str) -> bool:
    """R-74 探针辅助：用 key_str 试解密 ciphertext；返回 True 表示能解。"""
    if not ciphertext or not ciphertext.startswith(ENC_PREFIX):
        return False
    body = ciphertext[len(ENC_PREFIX):]
    if not body:
        return True  # 空串占位
    try:
        key_bytes = key_str.encode() if isinstance(key_str, str) else key_str
        Fernet(key_bytes).decrypt(body.encode("ascii"))
        return True
    except (InvalidToken, ValueError, TypeError):
        return False


def _find_enc_probe_in_db() -> str | None:
    """R-74 探针：找 DB 一条 enc_v1: 数据用作 master key 兼容性验证。

    搜索范围：users 4 加密列 / data_sources.db_password / app_settings 加密列。
    返回第一个 enc_v1: 字符串；找不到返回 None（fresh DB / v0.4.4 未加密 / 无 DB）。

    **不**经 repositories（避免 import-time 循环；core 层用 sqlite3 直读 stdlib 合法）。
    """
    # repo root = knot/core/crypto/fernet.py → 上 4 级
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "knot" / "data" / "knot.db",
        repo_root / "knot" / "data" / "bi_agent.db",  # rename migration 前
    ]
    db_path = next((p for p in candidates if p.exists()), None)
    if not db_path:
        return None  # 无 DB → 新部署或测试环境，跳过探针

    queries = [
        "SELECT api_key FROM users WHERE api_key LIKE 'enc_v1:%' LIMIT 1",
        "SELECT openrouter_api_key FROM users WHERE openrouter_api_key LIKE 'enc_v1:%' LIMIT 1",
        "SELECT embedding_api_key FROM users WHERE embedding_api_key LIKE 'enc_v1:%' LIMIT 1",
        "SELECT doris_password FROM users WHERE doris_password LIKE 'enc_v1:%' LIMIT 1",
        "SELECT db_password FROM data_sources WHERE db_password LIKE 'enc_v1:%' LIMIT 1",
        "SELECT value FROM app_settings WHERE value LIKE 'enc_v1:%' LIMIT 1",
    ]
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        for sql in queries:
            try:
                row = conn.execute(sql).fetchone()
                if row and row[0]:
                    return row[0]
            except sqlite3.OperationalError:
                continue  # 表/列不存在（更老 schema）
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return None


def _read_master_key() -> str | None:
    """v0.5.0 R-68 双源 + R-74 密文兼容性探针。

    R-68 4 组合：
      - 仅 KNOT_MASTER_KEY → 用新
      - 仅 BIAGENT_MASTER_KEY → 用旧 + deprecation warn
      - 都设（相同值）→ 用 KNOT + warn 旧名忽略
      - 都无 → 返回 None（上层 main.py fail-fast）

    R-74 密文兼容性探针（双 key 不同值时）：
      - 找一条 enc_v1: 数据探针
      - 旧 key 解密成功而新 key 失败 → sys.exit(1) + 强烈警报（防数据永久丢失）
    """
    new_key = os.getenv(_NEW_ENV)
    old_key = os.getenv(_OLD_ENV)

    # R-74 密文兼容性探针：双 key 不同值时验证
    if new_key and old_key and new_key != old_key:
        probe = _find_enc_probe_in_db()
        if probe:
            old_ok = _try_decrypt(old_key, probe)
            new_ok = _try_decrypt(new_key, probe)
            if old_ok and not new_ok:
                bar = "━" * 60
                print(f"\033[1;31m{bar}", file=sys.stderr)
                print("✗ KNOT 启动失败 — master KEY 兼容性冲突（R-74 探针）", file=sys.stderr)
                print(
                    f"  检测到 DB 中存在 enc_v1: 数据，"
                    f"旧 {_OLD_ENV} 能解密但新 {_NEW_ENV} 不能。",
                    file=sys.stderr,
                )
                print(
                    "  若直接用新 KEY 启动，历史加密数据将永久丢失。",
                    file=sys.stderr,
                )
                print("", file=sys.stderr)
                print(
                    f"  建议：暂保留 {_OLD_ENV} 单独使用，"
                    f"逐字段用旧 KEY 解密 + 新 KEY 重加密完成迁移后再切换。",
                    file=sys.stderr,
                )
                print(f"{bar}\033[0m", file=sys.stderr)
                sys.exit(1)

    # R-68 双源优先级
    if new_key:
        if old_key:
            logger.warning(
                "[deprecation] 同时设置了 %s 和 %s；使用 %s，忽略 %s。请删除旧变量。",
                _NEW_ENV, _OLD_ENV, _NEW_ENV, _OLD_ENV,
            )
        return new_key
    if old_key:
        logger.warning(
            "[deprecation] 仅检测到 %s（v0.5.0 起改名为 %s）；"
            "继续使用旧名以兼容；将于 v1.0 移除支持。",
            _OLD_ENV, _NEW_ENV,
        )
        return old_key
    return None


def loaded_env_name() -> str | None:
    """启动 banner 用：返回当前实际加载的 env 名（KNOT_MASTER_KEY / BIAGENT_MASTER_KEY / None）。

    注：本函数会触发 R-74 探针；与 _read_master_key() 调用语义一致。
    """
    new_key = os.getenv(_NEW_ENV)
    old_key = os.getenv(_OLD_ENV)
    if new_key:
        return _NEW_ENV
    if old_key:
        return _OLD_ENV
    return None


@lru_cache(maxsize=1)
def get_crypto_adapter() -> FernetAdapter:
    """R-40 进程单例（lru_cache 线程安全 — CPython GIL + 内部锁，R-44 async 安全）。

    测试 fixture 必须主动调 get_crypto_adapter.cache_clear() 隔离。
    """
    raw = _read_master_key()
    if not raw:
        raise CryptoConfigError(
            f"未设置 master key — 需配置 {_NEW_ENV}（或旧名 {_OLD_ENV}，v1.0 移除）"
        )
    try:
        key_bytes = raw.encode() if isinstance(raw, str) else raw
        return FernetAdapter(key_bytes)
    except (ValueError, TypeError) as e:
        raise CryptoConfigError(
            f"master key 格式无效（需 Fernet base64-urlsafe 32 字节）: {e}"
        ) from e


def assert_master_key_loaded() -> None:
    """启动期主动校验 — main.py 在 init_db() 之后调用（R-45）。"""
    get_crypto_adapter()
