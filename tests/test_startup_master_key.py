"""tests/test_startup_master_key.py — v0.4.5 R-45 启动期 master key 守护。

R-45：assert_master_key_loaded() 在 init_db() 之后；
缺失/格式错 → CryptoConfigError；上层 main.py 捕获后 sys.exit(1) + 彩色错误。
"""
import pytest

from bi_agent.core.crypto.fernet import (
    CryptoConfigError,
    assert_master_key_loaded,
    get_crypto_adapter,
)


def test_startup_missing_master_key_fails(monkeypatch):
    """缺失 → CryptoConfigError。"""
    monkeypatch.delenv("BIAGENT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError):
        assert_master_key_loaded()


def test_startup_invalid_master_key_format_fails(monkeypatch):
    """格式错 → CryptoConfigError（非裸 ValueError）。"""
    monkeypatch.setenv("BIAGENT_MASTER_KEY", "x" * 10)  # 太短
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError, match="格式无效"):
        assert_master_key_loaded()


def test_startup_valid_master_key_succeeds():
    """conftest 默认 fixture 已设 valid key；启动校验通过。"""
    # autouse fixture 已 setenv + cache_clear
    assert_master_key_loaded()  # 不抛即通过


def test_R45_startup_missing_key_prints_friendly_error_and_exits_1():
    """R-45：subprocess 跑 main module，缺 master key 应：
    - exit code 1（不是 0 / 非 1）
    - stderr 含 ━ 边框 + BIAGENT_MASTER_KEY 提示 + 生成命令
    - stderr **不**含 'Traceback' 长堆栈（友好错误 vs 裸异常）
    """
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env.pop("BIAGENT_MASTER_KEY", None)

    proc = subprocess.run(
        [sys.executable, "-c", "from bi_agent.main import app"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 1, f"应 sys.exit(1)，实际 {proc.returncode}"
    assert "━" in proc.stderr, "应见彩色边框（━ 字符）"
    assert "BIAGENT_MASTER_KEY" in proc.stderr, "应提示环境变量名"
    assert "Fernet.generate_key" in proc.stderr, "应提示生成命令"
    assert "Traceback" not in proc.stderr, "R-45：应友好错误，不暴露 traceback"
