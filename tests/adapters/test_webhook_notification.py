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


def test_send_makes_zero_network_attempt_for_non_allowlist_host(monkeypatch, no_network):
    """⭐ 非 allowlist host ⇒ **零出网尝试**（v0.9.18 P-a0 重写 —— 原名 `test_send_rejects_non_allowlist`）。

    ⚠️ **为什么改名 + 换判据（v3.1-B #8：断言仍值钱，过期的是理由）**：
    原判据是 `pytest.raises(wh.WebhookError)`，而它**因为错误的理由而绿** ——
    `webhook.py` 的 `except requests.RequestException: raise WebhookError(...)` 把**网络失败**
    也包成同一个异常类型 ⇒ 摘掉 allowlist 那道门后：
      `requests.post("https://other.com/x")` → 连不上 → `RequestException` → `WebhookError`
      ⇒ **`pytest.raises` 照样通过。**
    **实测（v0.9.18 P-a0，把守卫改成 `if False:`）**：本文件 **5 passed** —— 门没了而测全绿。

    ⚠️⚠️ **而且它更坏**：那条路径上 `no_network` 缺席（本文件此前 0 处引用，且该 fixture **非 autouse**）
    ⇒ 门一坏，**测试套件会真的向 `other.com` 发 POST**。

    ⇒ 新判据锚在「系统真的做了什么」而不是「抛没抛」：**`no_network` 记录列表必须为空**。
    异常仍断（它是用户可见行为），但**它不再是主 oracle** —— 主 oracle 是零出网。
    revert-to-bad：把守卫改成 `if False:` ⇒ 本测红在 `no_network` 探针的
    `AssertionError: ❌ 发生了真实网络请求 —— 出网门失效`，而不是含糊的「没抛异常」。
    """
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    try:
        wh.WebhookNotificationAdapter().send(Notification(title="t", body="b", target="https://other.com/x"))
    except Exception:                      # noqa: BLE001 —— 类型不是本测要断的东西，见下
        pass
    # ⭐ **主 oracle：一次网络尝试都不许有**（无条件执行，不挂在异常路径上 —— v3.1-C 五问①）
    assert no_network == [], (
        f"非 allowlist host 却发生了 {len(no_network)} 次出网尝试：{no_network}\n"
        "⇒ allowlist 那道门没能拦在 `requests.post` 之前。"
    )


def test_send_rejects_non_allowlist_with_actionable_message(monkeypatch, no_network):
    """次要断言：拒绝时给出**可操作**的说明（与上一条分开 —— 上一条守「零出网」，本条守「说得清」）。

    ⚠️ 拆成两条是刻意的：合在一起时，`pytest.raises` 会先满足，
    「零出网」那句 assert 就**永远不会执行**（v0.9.6 学到的形状：精心写的断言挂在不会到达的路径上）。
    """
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    with pytest.raises(wh.WebhookError) as ei:
        wh.WebhookNotificationAdapter().send(Notification(title="t", body="b", target="https://other.com/x"))
    msg = str(ei.value)
    assert "other.com" in msg, f"说明里没点名被拒的 host，运维无从排障：{msg!r}"
    # ⛔ 不得回显 allowlist 内容（#262 同族：整份内网主机清单不得经异常流回租户 admin）
    assert "hooks.example.com" not in msg, f"拒绝消息泄漏了 allowlist 内容：{msg!r}"


def test_send_posts_to_allowed(monkeypatch):
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    calls = {}

    class _Resp:
        # ⭐ v0.9.21：出站点新增「显式判 3xx」⇒ 假响应必须有 status_code
        #    （`raise_for_status()` 对 3xx **不抛** ⇒ 不显式判会把「没投递」当成功）。
        status_code = 200

        def raise_for_status(self):
            pass

    import requests
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.update(url=url, json=kw.get("json"), kw=kw) or _Resp())
    wh.WebhookNotificationAdapter().send(Notification(title="GMV 异动", body="跌 20%", level="warn",
                                                      target="https://hooks.example.com/abc"))
    # ⭐ v0.9.21：**断言禁令真的传了** —— 否则本测只证明「没炸」，
    #    有人摘掉 `allow_redirects=False` 它照样绿（v3.1-B #8「因错误的理由而绿」）。
    assert calls["kw"].get("allow_redirects") is False, (
        f"webhook POST 未传 allow_redirects=False：{calls['kw']}"
    )
    assert calls["url"] == "https://hooks.example.com/abc"
    assert calls["json"]["title"] == "GMV 异动" and calls["json"]["level"] == "warn"


# ─── v0.9.18 P-a · 租户域化后的**发送路径**（非起源租户）────────────────
def _ctx(tid: int, **extra):
    from knot.core.tenant_context import set_active_tenant
    row = {"id": tid, "db_dir": "."}
    row.update(extra)
    return set_active_tenant(row)


def _reset(tok):
    from knot.core.tenant_context import reset_active_tenant
    reset_active_tenant(tok)


def _non_owner_tid() -> int:
    from knot.core.tenant_context import OWNER_TENANT_ID
    return OWNER_TENANT_ID + 1


def test_non_owner_with_own_allowlist_really_sends(monkeypatch):
    """⭐ **正对照**：非起源租户配了自己的 allowlist ⇒ 请求**真的发出**。

    ⚠️ **为什么必须有这一条**：只测「拒绝」的话，一个「拦住所有人」的实现会**全绿**
    —— 那是 fail-closed 的假通过（v0.9.7 立的形状）。
    ⚠️ **刻意不 stub `send`**（Stage 2 S1）：既有 e2e `tests/api/test_monitors_admin.py:82`
    直接 `monkeypatch.setattr(WebhookNotificationAdapter, "send", ...)` **把被测适配器整个换掉**
    ⇒ 沿用那个 fixture 写本测必假绿。此处只 stub `requests.post`，被测代码路径完整执行。
    revert-to-bad：`get_webhook_allowed_hosts` 改回读 env ⇒ 非起源租户的 host 不在 env 里 ⇒ 本测红。
    """
    import requests
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "owner-only.example.com")   # 故意**不含**下面那个 host
    sent = {}

    class _Resp:
        # ⭐ v0.9.21：出站点新增「显式判 3xx」⇒ 假响应必须有 status_code
        #    （`raise_for_status()` 对 3xx **不抛** ⇒ 不显式判会把「没投递」当成功）。
        status_code = 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "post",
                        lambda url, **kw: sent.update(url=url, kw=kw) or _Resp())
    tok = _ctx(_non_owner_tid(), allowed_webhook_hosts="hooks.tenant-b.example")
    try:
        wh.WebhookNotificationAdapter().send(
            Notification(title="t", body="b", target="https://hooks.tenant-b.example/x"))
    finally:
        _reset(tok)
    assert sent.get("url") == "https://hooks.tenant-b.example/x", (
        "非起源租户配了自己的 allowlist，请求却没发出 —— 域化没生效，或实现变成了「拦住所有人」"
    )


def test_non_owner_with_null_column_makes_zero_network_attempt(monkeypatch, no_network):
    """⭐ 非起源租户**未配置**（列为 NULL）⇒ 全拒 + **零出网尝试**（fail-closed）。

    ⚠️ 主 oracle 是出网探针记录列表，**不是**「抛了 WebhookError」——
    后者分不清「被 allowlist 拒」与「网络连不上」（P-a0 清掉的正是那个形状）。
    revert-to-bad：删掉 `is_owner_tenant()` 那一支 ⇒ 非起源租户也回退 env
    ⇒ 若 env 里恰好有该 host 就会真的发出去 ⇒ 本测红。
    """
    monkeypatch.setenv("KNOT_WEBHOOK_ALLOWED_HOSTS", "hooks.tenant-b.example")   # env 里**有**它
    tok = _ctx(_non_owner_tid())                                                 # 但该租户列为 NULL
    try:
        try:
            wh.WebhookNotificationAdapter().send(
                Notification(title="t", body="b", target="https://hooks.tenant-b.example/x"))
        except Exception:                      # noqa: BLE001 —— 类型不是本测要断的
            pass
    finally:
        _reset(tok)
    assert no_network == [], (
        f"非起源租户未配置 allowlist，却发生了 {len(no_network)} 次出网尝试：{no_network}\n"
        "⇒ 它落回了进程 env = 用部署方的白名单给客租户放权。"
    )
