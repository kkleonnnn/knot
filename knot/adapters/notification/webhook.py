"""knot.adapters.notification.webhook — WebhookNotificationAdapter（v0.7.7 C3）。

兑现 base.py（v0.3.2 起预留无实现）NotificationAdapter Protocol：POST n.target（webhook URL）。

⚠️ **R-SL-69 独立 egress allowlist**：webhook target host 必须在 **`KNOT_WEBHOOK_ALLOWED_HOSTS`**
（独立 env）—— **严禁混用数据源读取 allowlist `KNOT_HTTP_ALLOWED_HOSTS`**（那是 KNOT 从哪些 host
**读**业务数据的边界；混用 → 通知 host 被允许读数据 = 污染数据源攻击面）。读取源 env ≠ 外发目标 env，
两个安全边界物理分离（守护者 Stage 3 F1）。
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from knot.adapters.notification.base import Notification

_WEBHOOK_TIMEOUT_SEC = 5


class WebhookError(Exception):
    """webhook 发送失败（非 allowlist / POST 失败）。"""


def get_webhook_allowed_hosts() -> set[str]:
    """读独立 env `KNOT_WEBHOOK_ALLOWED_HOSTS`（R-SL-69；≠ 数据源 KNOT_HTTP_ALLOWED_HOSTS）。未设 = 全拒。"""
    raw = os.environ.get("KNOT_WEBHOOK_ALLOWED_HOSTS", "")
    if not raw:
        return set()
    return {h.strip() for h in raw.split(",") if h.strip()}


def is_webhook_url_allowed(url: str) -> bool:
    """webhook target host 是否在 KNOT_WEBHOOK_ALLOWED_HOSTS（host-only，复用 url_allowlist 同模式，独立 env）。"""
    if not url:
        return False
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return bool(host) and host in get_webhook_allowed_hosts()


class WebhookNotificationAdapter:
    """NotificationAdapter Protocol 实现：POST webhook（独立 allowlist 守护 R-SL-69）。send 失败抛 WebhookError。"""

    def send(self, n: Notification) -> None:
        if not is_webhook_url_allowed(n.target):
            raise WebhookError(
                f"webhook host 不在 KNOT_WEBHOOK_ALLOWED_HOSTS 内: {n.target!r}"
                "（独立 egress allowlist；勿混用数据源 KNOT_HTTP_ALLOWED_HOSTS）"
            )
        import requests  # 延迟 import（与 http executor 同库；本机无亦不阻断 import）

        try:
            resp = requests.post(
                n.target,
                json={"title": n.title, "body": n.body, "level": n.level},
                timeout=_WEBHOOK_TIMEOUT_SEC,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise WebhookError(f"webhook POST 失败: {e}") from e
