"""knot.adapters.notification — 通知适配层（v0.3.2 占位 / 飞书将先落地）

资深路线：飞书是唯一高优；Slack/钉钉暂无明确需求但接口要预留。
本 PATCH 仅落 Protocol + Lark stub（NotImplementedError），让接口形状先定，
未来加 impl 不动调用方。
"""
from knot.adapters.notification.base import Notification, NotificationAdapter  # noqa: F401
