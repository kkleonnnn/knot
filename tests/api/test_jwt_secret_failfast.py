"""tests/api/test_jwt_secret_failfast.py — v0.6.0.8 MUST-1 守护测试。

JWT_SECRET fail-fast 三场景：
- 缺失（env 完全没设）
- 历史默认占位（knot- / chatbi- / bi-agent-）
- 长度 < 16

正常路径：长度 ≥ 16 且非默认 → 返回该 secret。
"""
from __future__ import annotations

import pytest


def test_jwt_fail_when_missing(monkeypatch):
    """未设 JWT_SECRET → sys.exit(1)。"""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from knot.api.deps import _resolve_jwt_secret
    with pytest.raises(SystemExit) as excinfo:
        _resolve_jwt_secret()
    assert excinfo.value.code == 1


def test_jwt_fail_when_legacy_default(monkeypatch):
    """历史默认占位 → sys.exit(1)（公开仓 grep 可得，伪造 token 风险）。"""
    monkeypatch.setenv("JWT_SECRET", "knot-secret-change-in-production")
    from knot.api.deps import _resolve_jwt_secret
    with pytest.raises(SystemExit) as excinfo:
        _resolve_jwt_secret()
    assert excinfo.value.code == 1


def test_jwt_fail_when_chatbi_legacy(monkeypatch):
    """v0.2.x chatbi 期遗留命名 → sys.exit(1)。"""
    monkeypatch.setenv("JWT_SECRET", "chatbi-secret-change-in-production")
    from knot.api.deps import _resolve_jwt_secret
    with pytest.raises(SystemExit) as excinfo:
        _resolve_jwt_secret()
    assert excinfo.value.code == 1


def test_jwt_fail_when_too_short(monkeypatch):
    """长度 < 16 → sys.exit(1)（防 'test' 这种短到爆破的值）。"""
    monkeypatch.setenv("JWT_SECRET", "short")
    from knot.api.deps import _resolve_jwt_secret
    with pytest.raises(SystemExit) as excinfo:
        _resolve_jwt_secret()
    assert excinfo.value.code == 1


def test_jwt_pass_when_valid(monkeypatch):
    """合规 secret（≥16 字符 + 非默认）→ 返回原值。"""
    valid = "production-grade-jwt-secret-32-chars"
    monkeypatch.setenv("JWT_SECRET", valid)
    from knot.api.deps import _resolve_jwt_secret
    result = _resolve_jwt_secret()
    assert result == valid
