"""飞书（Lark）通知 stub（v0.3.2）。

仅占位 — NotImplementedError。等业务真正接入飞书时（v0.4.x 或更晚）：
1. 配置 LARK_WEBHOOK_URL
2. 实现 send() 用 requests 调 Webhook V2 API
3. 加 retry / signature signing 等

接口契约（NotificationAdapter Protocol）已锁定，业务调用方可 mock 写测试。
"""
from __future__ import annotations

from bi_agent.adapters.notification.base import Notification, NotificationAdapter


class LarkAdapter:
    """实现 NotificationAdapter Protocol（v0.3.2 占位）。"""

    def __init__(self, webhook_url: str = "", secret: str = ""):
        self._webhook = webhook_url
        self._secret = secret

    def send(self, n: Notification) -> None:
        raise NotImplementedError(
            "LarkAdapter.send 暂未实现（v0.3.2 仅锁接口形状）。"
            "业务接入飞书时按 NotificationAdapter Protocol 实现 send()。"
        )


_check: NotificationAdapter = LarkAdapter()
