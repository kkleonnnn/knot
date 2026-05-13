"""tests/conftest.py — 全局 fixture（v0.4.5 R-37 master key 隔离 + tmp_db_path）。

R-37：测试 master key 用 monkeypatch.setenv + autouse fixture 隔离；
严禁 import-time 污染生产 env。所有测试默认拿到一个固定的测试 key，
单独需要测「缺失 / 无效」场景的测试用 monkeypatch.delenv / setenv 自己覆盖。
"""
import os
import tempfile

import pytest

# 固定测试 master key — 守护者 Q4 决策：硬编码胜过 env-driven。
# ⚠️ 该 key 仅用于测试；严禁用于任何生产环境 / staging / 真实部署。
# 该 key 不是 secret — 任何人均可调 Fernet.generate_key() 产出等价 key；
# 硬编码是为测试可重现性（避免 CI 多 worker / 并行测试时 env 污染）。
# 移除/改动测试时需同步更新。
TEST_MASTER_KEY = "QwlGZIGjzEryd93omq5UGR5ATZ6mTMm70NmS4o331Xk="


@pytest.fixture(autouse=True)
def _master_key_for_tests(monkeypatch):
    """为每个测试默认设置 KNOT_MASTER_KEY；清空 lru_cache 防 fixture 间污染（R-40）。

    v0.6.0 F13/F14.2 单源化：直接走 KNOT_MASTER_KEY 路径
    （v0.5.0 双源兼容已撤回；test_env_dual_source.py 已删）。
    """
    monkeypatch.setenv("KNOT_MASTER_KEY", TEST_MASTER_KEY)
    # 清 lru_cache（防上一测试持有了不同 key 的 adapter）
    try:
        from knot.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass  # commit #1 之前 crypto 模块还没建
    yield
    try:
        from knot.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass


@pytest.fixture()
def tmp_db_path(monkeypatch):
    """临时 SQLite — repositories / scripts 测试共用（v0.4.5 hoist）。

    base.py 在 import 时把 SQLITE_DB_PATH 拷进自己的命名空间，所以 monkeypatch
    必须直接打 base 模块（不是 config 单例）。
    """
    fd, path = tempfile.mkstemp(suffix=".db", prefix="knot_test_")
    os.close(fd)
    os.unlink(path)  # 让 init_db() 自己创建

    from knot.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()

    yield path

    if os.path.exists(path):
        os.unlink(path)
