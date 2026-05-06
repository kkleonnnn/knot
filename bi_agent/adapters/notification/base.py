"""通知适配契约（v0.3.2）。

Go interface 1:1：
    type NotificationAdapter interface {
        Send(n Notification) error
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

NotificationLevel = Literal["info", "warn", "error"]


@dataclass
class Notification:
    title: str
    body: str
    level: NotificationLevel = "info"
    target: str = ""  # 渠道/群 ID / webhook 等，按 adapter 自解释
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class NotificationAdapter(Protocol):
    """通知发送契约。"""

    def send(self, n: Notification) -> None:
        """同步发送；失败抛异常（不返 sentinel value）。"""
        ...
