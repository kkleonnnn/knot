"""tests/adapters/test_webhook_notification.py — v0.7.7 C3 WebhookNotificationAdapter 守护。

R-SL-69 独立 egress allowlist（KNOT_WEBHOOK_ALLOWED_HOSTS ≠ 数据源 KNOT_HTTP_ALLOWED_HOSTS）+
NotificationAdapter Protocol 实现 + 非 allowlist 拒发 + secure-by-default + POST 成功路径。
"""
import pytest

from knot.adapters.notification import webhook as wh
from knot.adapters.notification.base import Notification, NotificationAdapter


def test_satisfies_protocol():
    assert isinstance(wh.WebhookNotificationAdapter(), NotificationAdapter)   # 兑现预留 Protocol


def test_independent_allowlist_not_http(monkeypatch):
    """R-SL-69：webhook 读 KNOT_WEBHOOK_ALLOWED_HOSTS，**不读**数据源 KNOT_HTTP_ALLOWED_HOSTS（边界分离）。"""
    monkeypatch.setenv("KNOT_HTTP_ALLOWED_HOSTS", "evil-datasource.com")      # 数据源读取 allowlist
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")     # webhook 外发 allowlist
    assert wh.is_webhook_url_allowed("https://hooks.example.com/x") is True
    assert wh.is_webhook_url_allowed("https://evil-datasource.com/x") is False  # 数据源 host 不被 webhook 放行（不混用）


def test_empty_env_denies_all(monkeypatch):
    monkeypatch.delenv("KNOT_WEBHOOK_ALLOWED_HOSTS", raising=False)
    assert wh.is_webhook_url_allowed("https://hooks.example.com/x") is False   # secure by default（未配 = 全拒）


def test_send_rejects_non_allowlist(monkeypatch):
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    with pytest.raises(wh.WebhookError):
        wh.WebhookNotificationAdapter().send(Notification(title="t", body="b", target="https://other.com/x"))


def test_send_posts_to_allowed(monkeypatch):
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    calls = {}

    class _Resp:
        def raise_for_status(self):
            pass

    import requests
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: calls.update(url=url, json=json) or _Resp())
    wh.WebhookNotificationAdapter().send(Notification(title="GMV 异动", body="跌 20%", level="warn",
                                                      target="https://hooks.example.com/abc"))
    assert calls["url"] == "https://hooks.example.com/abc"
    assert calls["json"]["title"] == "GMV 异动" and calls["json"]["level"] == "warn"
