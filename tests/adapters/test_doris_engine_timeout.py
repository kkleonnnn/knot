"""tests/adapters/test_doris_engine_timeout.py — v0.7.42 B2.2 回归守护。

Doris engine 加 read_timeout（socket 读超时守护）：
- create_engine 把 read_timeout=DORIS_READ_TIMEOUT 传入 connect_args
- 既有 connect_args（ssl_disabled/connect_timeout）+ pool 参数 byte-equal 保留
- 默认 60s + KNOT_DORIS_READ_TIMEOUT env 可覆盖（守护者 R5.2）
"""
from __future__ import annotations

import importlib


def test_create_engine_wires_read_timeout(monkeypatch):
    """create_engine 将 read_timeout 传入 connect_args；既有参数不动。"""
    from knot.adapters.db import doris
    from knot.config import DORIS_READ_TIMEOUT

    captured = {}

    def _fake(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(doris.sqlalchemy, "create_engine", _fake)

    doris.create_engine("h", 9030, "u", "p", "db")

    ca = captured["kwargs"]["connect_args"]
    assert ca["read_timeout"] == DORIS_READ_TIMEOUT
    # 既有 connect_args + pool 参数 byte-equal 保留（无回归）
    assert ca["ssl_disabled"] is True
    assert ca["connect_timeout"] == 3
    assert captured["kwargs"]["pool_recycle"] == 3600
    assert captured["kwargs"]["pool_pre_ping"] is True


def test_doris_read_timeout_default_is_60():
    """默认 60s（守护者背书 + kk 确认；够宽不误杀 information_schema 慢加载）。"""
    from knot.config import DORIS_READ_TIMEOUT

    assert DORIS_READ_TIMEOUT == 60


def test_doris_read_timeout_env_override(monkeypatch):
    """KNOT_DORIS_READ_TIMEOUT env 覆盖默认（R5.2）。"""
    import sys

    # 注意：`from knot.config import settings` 拿到的是单例对象（被 __init__ re-export 遮蔽），
    # 非模块 → reload 报错。用 sys.modules 取真实 settings 模块。
    settings_mod = sys.modules["knot.config.settings"]

    monkeypatch.setenv("KNOT_DORIS_READ_TIMEOUT", "15")
    importlib.reload(settings_mod)
    try:
        assert settings_mod.DORIS_READ_TIMEOUT == 15
    finally:
        monkeypatch.delenv("KNOT_DORIS_READ_TIMEOUT", raising=False)
        importlib.reload(settings_mod)  # 复原默认，防污染后续测试
