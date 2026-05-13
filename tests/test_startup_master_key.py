"""tests/test_startup_master_key.py — v0.4.5 R-45 启动期 master key 守护。

R-45：assert_master_key_loaded() 在 init_db() 之后；
缺失/格式错 → CryptoConfigError；上层 main.py 捕获后 sys.exit(1) + 彩色错误。

v0.6.0 F14.4：v0.5.0 R-68 双源相关 case 已撤回（commit 4 fernet.py 单源化）；
本文件保留 R-45 单源核心 case + subprocess boot smoke。
"""
import pytest

from knot.core.crypto.fernet import (
    CryptoConfigError,
    assert_master_key_loaded,
    get_crypto_adapter,
)


def test_startup_missing_master_key_fails(monkeypatch):
    """缺失 → CryptoConfigError。"""
    monkeypatch.delenv("KNOT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError):
        assert_master_key_loaded()


def test_startup_invalid_master_key_format_fails(monkeypatch):
    """格式错 → CryptoConfigError（非裸 ValueError）。"""
    monkeypatch.setenv("KNOT_MASTER_KEY", "x" * 10)  # 太短
    get_crypto_adapter.cache_clear()
    with pytest.raises(CryptoConfigError, match="格式无效"):
        assert_master_key_loaded()


def test_startup_valid_master_key_succeeds():
    """conftest 默认 fixture 已设 valid key；启动校验通过。"""
    # autouse fixture 已 setenv + cache_clear
    assert_master_key_loaded()  # 不抛即通过


def test_R45_startup_missing_key_prints_friendly_error_and_exits_1(tmp_path):
    """R-45：subprocess 跑 main module，缺 master key 应：
    - exit code 1（不是 0 / 非 1）
    - stderr 含 ━ 边框 + master key 环境变量名提示 + 生成命令
    - stderr **不**含 'Traceback' 长堆栈（友好错误 vs 裸异常）

    v0.6.0 单源 + dotenv 隔离：cwd=tmp_path 防 settings.py load_dotenv()
    向上找到 worktree 父目录的 .env 自动注入 KNOT_MASTER_KEY。
    """
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env.pop("KNOT_MASTER_KEY", None)

    # cwd=tmp_path 隔离 .env 自动发现（worktree 父目录有 .env 含 KNOT_MASTER_KEY）；
    # 同时通过 PYTHONPATH 注入 worktree 让 knot 模块仍可 import
    from pathlib import Path
    worktree_root = Path(__file__).resolve().parent.parent
    env["PYTHONPATH"] = str(worktree_root) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [sys.executable, "-c", "from knot.main import app"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(tmp_path),
        check=False,
    )
    assert proc.returncode == 1, f"应 sys.exit(1)，实际 {proc.returncode}\n stderr: {proc.stderr[:400]}"
    assert "━" in proc.stderr, "应见彩色边框（━ 字符）"
    # v0.6.0 F14.4：单源化后仅检测 KNOT_MASTER_KEY 字面
    assert "KNOT_MASTER_KEY" in proc.stderr, \
        "应提示环境变量名 KNOT_MASTER_KEY"
    assert "Fernet.generate_key" in proc.stderr, "应提示生成命令"
    assert "Traceback" not in proc.stderr, "R-45：应友好错误，不暴露 traceback"
