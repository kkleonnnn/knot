"""adapters/notification 契约单测（v0.5.5 清理：lark stub 已删除，仅保留 Notification dataclass 契约测试）。"""
from knot.adapters.notification.base import Notification


def test_notification_dataclass_defaults():
    n = Notification(title="t", body="b")
    assert n.level == "info"
    assert n.target == ""
    assert n.metadata == {}
