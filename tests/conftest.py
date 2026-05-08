"""tests/conftest.py — 全局 fixture（v0.4.5 R-37 master key 隔离）。

R-37：测试 master key 用 monkeypatch.setenv + autouse fixture 隔离；
严禁 import-time 污染生产 env。所有测试默认拿到一个固定的测试 key，
单独需要测「缺失 / 无效」场景的测试用 monkeypatch.delenv / setenv 自己覆盖。
"""
import pytest

# 固定测试 key（仅用于测试 — 不是生产；commit 中以明文出现是安全的，因为它不保护任何真实数据）
TEST_MASTER_KEY = "QwlGZIGjzEryd93omq5UGR5ATZ6mTMm70NmS4o331Xk="


@pytest.fixture(autouse=True)
def _master_key_for_tests(monkeypatch):
    """为每个测试默认设置 BIAGENT_MASTER_KEY；清空 lru_cache 防 fixture 间污染（R-40）。"""
    monkeypatch.setenv("BIAGENT_MASTER_KEY", TEST_MASTER_KEY)
    # 清 lru_cache（防上一测试持有了不同 key 的 adapter）
    try:
        from bi_agent.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass  # commit #1 之前 crypto 模块还没建
    yield
    try:
        from bi_agent.core.crypto.fernet import get_crypto_adapter
        get_crypto_adapter.cache_clear()
    except ImportError:
        pass
