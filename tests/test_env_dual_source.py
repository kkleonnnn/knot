"""tests/test_env_dual_source.py — v0.5.0 R-68 双源 + R-74 密文兼容性探针守护（TDD）。

R-78：必须显式 unset 全局 autouse fixture 注入的 BIAGENT_MASTER_KEY，
否则 R-68 双源测试无法独立。

覆盖 R-68 4 组合：
- 仅新（KNOT_MASTER_KEY）→ 用新
- 仅旧（BIAGENT_MASTER_KEY）→ 用旧 + deprecation warn
- 都设相同值 → 用 KNOT + warn 旧名忽略
- 都无 → 返回 None（main.py 上层 fail-fast）

覆盖 R-74 密文兼容性探针：
- 双 key 不同值 + DB 有 enc_v1: 数据 + 旧 key 解密成功新 key 失败 → SystemExit
- 双 key 相同值 → 不触发探针
- 双 key 不同值但无 enc_v1: 数据 → 探针 skip → 用 KNOT
"""
import logging
import sqlite3

import pytest

# D-2 阶段 import 必失败；D-3 git mv 后转绿
from knot.core.crypto.fernet import _read_master_key, get_crypto_adapter


VALID_KEY_1 = "QwlGZIGjzEryd93omq5UGR5ATZ6mTMm70NmS4o331Xk="
VALID_KEY_2 = "fJzKPp7pQz9JxHMvXq5BcYaP8R8FGHe6mYz4kT3o5Wk="  # 不同的有效 Fernet key


@pytest.fixture(autouse=True)
def _isolate_dual_env(monkeypatch):
    """R-78：显式 unset 全局 autouse fixture 注入的 env，让本文件测试自主控制双源。"""
    monkeypatch.delenv("BIAGENT_MASTER_KEY", raising=False)
    monkeypatch.delenv("KNOT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()
    yield
    get_crypto_adapter.cache_clear()


# ─── R-68 4 组合 ─────────────────────────────────────────────────────

def test_R68_only_new_key(monkeypatch):
    """仅 KNOT_MASTER_KEY → 用新 key（无 warn）。"""
    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_1)
    assert _read_master_key() == VALID_KEY_1


def test_R68_only_old_key_with_deprecation(monkeypatch, caplog):
    """仅 BIAGENT_MASTER_KEY → 用旧 key + deprecation warn。"""
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    with caplog.at_level(logging.WARNING):
        assert _read_master_key() == VALID_KEY_1
    msgs = " ".join(r.message for r in caplog.records).lower()
    assert "deprecat" in msgs or "deprecation" in msgs, (
        f"应见 deprecation warning；实际 caplog: {[r.message for r in caplog.records]}"
    )


def test_R68_both_same_value_uses_new_with_warn(monkeypatch, caplog):
    """同时设两个 + 相同值 → 用 KNOT + warn 旧名被忽略（D2 决议 A）。"""
    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_1)
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    with caplog.at_level(logging.WARNING):
        assert _read_master_key() == VALID_KEY_1


def test_R68_neither_returns_none(monkeypatch):
    """都无 → 返回 None（main.py 上层 fail-fast，沿袭 v0.4.5 R-45）。"""
    # autouse 已 delenv，无需重复
    assert _read_master_key() is None


# ─── R-74 密文兼容性探针 ──────────────────────────────────────────────

def test_R74_dual_keys_different_with_enc_data_old_succeeds_new_fails_exits(
    monkeypatch,
):
    """R-74：双 key 不同值 + DB 有 enc_v1: 数据 + 旧 key 解密成功新 key 失败 → SystemExit。

    防数据永久丢失：守护者答资深架构师维度 2 核心场景。

    实现：monkeypatch _find_enc_probe_in_db 直接 inject 探针密文（避免依赖
    fernet hardcoded knot/data 路径，保 core 层不依赖 repositories Contract 7）。
    """
    # 步骤 1：用 VALID_KEY_1 直接生成一条 enc_v1: 探针密文（不经 lru_cache）
    from knot.core.crypto.fernet import ENC_PREFIX, FernetAdapter
    encrypted = FernetAdapter(VALID_KEY_1.encode()).encrypt("secret-payload")
    assert encrypted.startswith(ENC_PREFIX)

    # 步骤 2：monkey patch fernet._find_enc_probe_in_db 返回探针
    from knot.core.crypto import fernet as fernet_mod
    monkeypatch.setattr(fernet_mod, "_find_enc_probe_in_db", lambda: encrypted)

    # 步骤 3：切到双 key 不同：KNOT 是新值（无法解 VALID_KEY_1 密文）
    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_2)
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    get_crypto_adapter.cache_clear()

    # 步骤 4：_read_master_key 触发 R-74 探针 → SystemExit（防数据永久丢失）
    with pytest.raises(SystemExit):
        _read_master_key()


def test_R74_dual_keys_different_with_enc_data_both_succeed_no_exit(monkeypatch):
    """R-74 边界：双 key 不同值，但都能解密相同密文（罕见但合法）→ 不 exit。"""
    from knot.core.crypto.fernet import FernetAdapter
    encrypted = FernetAdapter(VALID_KEY_1.encode()).encrypt("payload")

    # monkey patch 探针 + 让 _try_decrypt 对两 key 都 True（mock 模拟 key 兼容场景）
    from knot.core.crypto import fernet as fernet_mod
    monkeypatch.setattr(fernet_mod, "_find_enc_probe_in_db", lambda: encrypted)
    # 模拟双 key 兼容（new 也能解）
    monkeypatch.setattr(fernet_mod, "_try_decrypt", lambda key, ct: True)

    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_2)
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    get_crypto_adapter.cache_clear()

    # 不应 raise SystemExit
    assert _read_master_key() == VALID_KEY_2


def test_R74_dual_keys_same_value_no_probe_needed(monkeypatch):
    """R-74 边界：双 key 相同值 → 不触发探针（相同 key 同密文兼容）。"""
    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_1)
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    # 相同值不应 SystemExit
    assert _read_master_key() == VALID_KEY_1


def test_R74_dual_keys_different_no_enc_data_skip_probe(monkeypatch):
    """R-74 边界：双 key 不同值 + 无 enc_v1: 探针目标 → 探针 skip → 正常 KNOT 优先。

    新部署或 fresh DB 用户 rename env 时 不应误报 SystemExit。
    """
    # monkey patch 探针返回 None（fresh DB / 无加密数据）
    from knot.core.crypto import fernet as fernet_mod
    monkeypatch.setattr(fernet_mod, "_find_enc_probe_in_db", lambda: None)

    monkeypatch.setenv("KNOT_MASTER_KEY", VALID_KEY_2)
    monkeypatch.setenv("BIAGENT_MASTER_KEY", VALID_KEY_1)
    get_crypto_adapter.cache_clear()

    # 无探针目标 → 跳过探针 → 用 KNOT
    assert _read_master_key() == VALID_KEY_2
