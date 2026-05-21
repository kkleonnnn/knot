"""v0.6.0.15 — CORS env 配置守护测试。

KNOT_CORS_ORIGINS 行为：
- 未设 / 空字符串 → ["*"] + allow_credentials=False（CORS 规范）
- 显式逗号分隔 → list + allow_credentials=True

由于 _cors_origins 在 main.py 模块级求值，需在 import 前设 env；
使用 importlib.reload 重载模块以测试不同 env 组合。
"""

import importlib
import os

import pytest


def _reload_knot_main():
    """重新加载 knot.main 以重读 env（模块级常量）。"""
    import knot.main
    return importlib.reload(knot.main)


@pytest.fixture
def restore_cors_env(monkeypatch):
    """每个测试后清除 KNOT_CORS_ORIGINS 干扰。"""
    monkeypatch.delenv("KNOT_CORS_ORIGINS", raising=False)
    yield
    # monkeypatch 会自动还原


def test_cors_unset_defaults_to_star_no_credentials(restore_cors_env):
    """KNOT_CORS_ORIGINS 未设 → ["*"] + credentials=False（CORS 规范要求）。"""
    os.environ.pop("KNOT_CORS_ORIGINS", None)
    mod = _reload_knot_main()
    assert mod._cors_origins == ["*"]
    assert mod._cors_allow_credentials is False


def test_cors_empty_string_treated_as_unset(restore_cors_env, monkeypatch):
    """空字符串 / 空白也走兜底（防 .env 留 KNOT_CORS_ORIGINS= 空值误触发）。"""
    monkeypatch.setenv("KNOT_CORS_ORIGINS", "   ")
    mod = _reload_knot_main()
    assert mod._cors_origins == ["*"]
    assert mod._cors_allow_credentials is False


def test_cors_single_origin_enables_credentials(restore_cors_env, monkeypatch):
    """单个 origin → 启用 credentials（cookie / Authorization 透传必需）。"""
    monkeypatch.setenv("KNOT_CORS_ORIGINS", "https://knot.example.com")
    mod = _reload_knot_main()
    assert mod._cors_origins == ["https://knot.example.com"]
    assert mod._cors_allow_credentials is True


def test_cors_multi_origin_parsed_and_trimmed(restore_cors_env, monkeypatch):
    """逗号分隔多 origin + 自动 trim 空白。"""
    monkeypatch.setenv(
        "KNOT_CORS_ORIGINS",
        " https://knot.example.com , https://app.example.com ,  ",
    )
    mod = _reload_knot_main()
    assert mod._cors_origins == ["https://knot.example.com", "https://app.example.com"]
    assert mod._cors_allow_credentials is True


def test_cors_middleware_registered():
    """CORSMiddleware 实际挂在 app.user_middleware 上（防 import 出错但 middleware 漏挂）。"""
    from fastapi.middleware.cors import CORSMiddleware

    mod = _reload_knot_main()
    middleware_classes = [m.cls for m in mod.app.user_middleware]
    assert CORSMiddleware in middleware_classes, (
        f"CORSMiddleware 未注册，实际挂载：{middleware_classes}"
    )
