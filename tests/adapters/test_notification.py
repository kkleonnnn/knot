"""adapters/notification 契约单测（v0.3.2 仅锁形状，Lark 是 stub）。"""
import pytest

from knot.adapters.notification import NotificationAdapter
from knot.adapters.notification.base import Notification
from knot.adapters.notification.lark import LarkAdapter


def test_notification_dataclass_defaults():
    n = Notification(title="t", body="b")
    assert n.level == "info"
    assert n.target == ""
    assert n.metadata == {}


def test_lark_satisfies_protocol():
    assert isinstance(LarkAdapter(), NotificationAdapter)


def test_lark_send_raises_not_implemented():
    """v0.3.2 仅占位；调用必须显式失败而非静默丢消息。"""
    a = LarkAdapter()
    with pytest.raises(NotImplementedError):
        a.send(Notification(title="t", body="b"))
