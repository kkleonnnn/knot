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


#: 平台库 `tenants` 的列名（真相源；派生断言 `tests/test_allowlist_column_registration.py` 读它）。
COLUMN_NAME = "allowed_webhook_hosts"
#: 起源租户未配置时的回退 env（**≠** 数据源那个 `KNOT_HTTP_ALLOWED_HOSTS`）。
ENV_NAME = "KNOT_WEBHOOK_ALLOWED_HOSTS"


def _parse(raw: str) -> set[str]:
    return {h.strip() for h in raw.split(",") if h.strip()}


def resolve_allowed_hosts() -> tuple[set[str], str]:
    """当前租户允许 webhook 外发的 host 集 + 来源标记（v0.9.18 P-a 租户域化）。

    ⭐ **与 `adapters/http/url_allowlist.get_allowed_hosts` 逐字同构** —— 刻意不自创第二套写法：
    两份 allowlist 的三态语义必须一致，否则运维要记两套规则，而**记错的那次不会报错**。

    **三态**（判据必须 `is None`）：
      · `NULL`  = 未配置 ⇒ **起源租户**回退 env（+启动 WARN）；**非起源租户全拒绝**
      · `''`    = 已配置为空 ⇒ 部署方**明确表达的「禁」**⇒ 全拒绝，**起源租户也不回退 env**
      · 非空    = 该 host 集本身（**永不与 env 或其他租户取交集/并集**）

    ⚠️ **必须 `.get()`，不得下标**（v0.9.7 must-fix M2）：ctx 契约只保证 `id`/`db_dir`；
    实测 `set_active_tenant(` 现 **128 处 / 15 文件**，含 `conftest.py` 的 **autouse** 行
    （只有 `{id,slug,name,status,db_dir}`）⇒ 下标会炸一大片。
    `.get()` → None → 非起源租户拒 / 起源租户回退 env，**两个方向都安全**。

    ⚠️⚠️ **判据严禁写成 `if raw:`**（M1）：那样 `''`（明确的「禁」）会落回 env
    ⇒ 静默变成「按 env 放行」。**这是本片唯一一个能把 fail-closed 写成 fail-open 的地方。**
    """
    from knot.core.tenant_context import current_tenant, is_owner_tenant

    raw = current_tenant().get(COLUMN_NAME)
    if raw is None:                                          # 未配置
        if not is_owner_tenant():
            return set(), "unconfigured"                     # 非起源租户 ⇒ 全拒绝
        return _parse(os.environ.get(ENV_NAME, "")), "env-fallback"
    return _parse(raw), "column"                             # 已配置（空 ⇒ 拒绝，且不回退）


def get_webhook_allowed_hosts() -> set[str]:
    """当前租户允许 webhook 外发的 host 集。

    ⭐ **签名刻意不变** ⇒ `is_webhook_url_allowed` 与唯一生产调用点（`api/admin/monitors.py`）
    **零改动跟随**（照 v0.9.7 的做法）。
    """
    return resolve_allowed_hosts()[0]


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
            # ⛔ **消息里不得出现 env 名 / 列名 / allowlist 内容**（v0.9.18 P-a · Stage 2 S8）：
            #    `monitors.py` 会把本异常的文本拼进 HTTP 响应**并落进租户库的 trigger 审计**
            #    ⇒ 任何这里写下的东西都到得了租户 admin 眼前（#262 同族）。
            # ⚠️ **原消息点名了 `KNOT_WEBHOOK_ALLOWED_HOSTS`** —— 租户域化后那句还**是误导的**：
            #    非起源租户的判据根本不是那个 env，而是它自己那一列。
            # ⇒ 诊断细节（来源是列还是 env、集合多大）只进服务端日志，**不进异常**。
            from knot.core.logging_setup import logger

            hosts, source = resolve_allowed_hosts()
            logger.warning(
                f"[webhook-egress] 拒绝外发：target 的 host 不在本租户 allowlist 内 "
                f"(source={source}, size={len(hosts)})"
            )
            raise WebhookError(f"webhook 目标 host 未被允许: {n.target!r}（请联系部署方配置外发白名单）")
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
