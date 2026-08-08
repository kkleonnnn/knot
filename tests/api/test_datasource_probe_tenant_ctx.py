"""数据源健康探测的**线程内租户上下文**（v0.9.19 C0 —— 修一个自 v0.9.7 起就在线上的缺陷）。

## 缺陷
`api/admin/datasources.py` 的 `/api/admin/datasources/status` 用
`loop.run_in_executor(pool, _test_source, s)` 并发探测，而 **`run_in_executor` 不传播 contextvars**。
本仓其余**三处** `run_in_executor` 全都写了 `copy_context().run`
（`bi_share.py` / `bi_reports.py` / `bi_schedule.py`，且都带 v0.9.0 C2 的显式注释）——
**唯独这一处漏了**。

⇒ 线程内 `current_tenant()` 抛 `TenantContextError`
⇒ `_test_source` 的 http 分支调 `is_url_allowed`（v0.9.7 起 per-tenant ⇒ 需要 ctx）时抛
⇒ 被 `except Exception: return "error"` 吞
⇒ **所有 HTTP 数据源在 admin 列表里恒显示 "error"，HTTP 200，无日志。**

## 为什么潜伏了一整个版本弧没被发现
既有测（`tests/integration/test_v0821_admin_fetch.py`）每个 `/status` 用例都
`monkeypatch.setattr(ds, "_test_source", …)` **把真函数整个换掉**
⇒ **真实 `_test_source` 函数体零测覆盖** ⇒ 修前修后那些测都绿。
⭐ 本文件的存在理由就是这个：**它必须跑到真函数**。

## 判据分两层，缺一不可
1. **单元层**：`_test_source` 在 executor 里跑时，`current_tenant()` **拿得到**当前租户。
2. **端点层**：`/status` 的返回值里，配置正确的源**不是** `"error"`。
   ⚠️ 只有第 1 层的话，「ctx 到了但别处又坏了」测不出来；
   只有第 2 层的话，`"error"` 有太多别的成因，**分不清是不是这个缺陷**。
"""
from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

import pytest

from knot.api.admin import datasources as ds
from knot.core.tenant_context import (
    TenantContextError,
    current_tenant,
    reset_active_tenant,
    set_active_tenant,
)


def test_run_in_executor_does_not_propagate_context_by_itself():
    """⭐ **先钉住那个前提**（否则下面两条测的是什么就说不清了）。

    这条不测生产代码，它测的是 **Python 的行为**：`run_in_executor` **不**传播 contextvars。
    ⚠️ 为什么值得单写一条：本仓已经有**四处**跨线程边界，其中一处漏了传播 ——
    如果哪天这个前提变了（Python 改行为 / 换了执行器），**其余三处的 `copy_context()` 就成了无用功**，
    而那时没人会知道。⇒ 让前提本身可被检验。
    """
    async def _probe_without_ctx():
        tok = set_active_tenant({"id": 1, "db_dir": "."})
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                def _read():
                    try:
                        return ("ok", current_tenant()["id"])
                    except TenantContextError:
                        return ("raised", None)
                bare = await loop.run_in_executor(pool, _read)
                ctx = contextvars.copy_context()
                wrapped = await loop.run_in_executor(pool, lambda: ctx.run(_read))
            return bare, wrapped
        finally:
            reset_active_tenant(tok)

    bare, wrapped = asyncio.run(_probe_without_ctx())
    assert bare == ("raised", None), (
        f"前提已变：裸 `run_in_executor` 竟然带上了 ctx（得到 {bare!r}）——\n"
        "⇒ 本仓四处 `copy_context()` 的理由需要重新评估。"
    )
    assert wrapped == ("ok", 1), f"`copy_context().run` 没能传播 ctx（得到 {wrapped!r}）"


def test_status_endpoint_probe_sees_tenant_context(client, auth_headers, monkeypatch):
    """⭐ **端点层**：经真 `/api/admin/datasources/status`，探测线程里**拿得到** tenant ctx。

    ⚠️⚠️ **初版这条测判别力为零，是跑 revert 才发现的**（本片最贵的一课，写在这里）：
    初版在**测里自己写了一遍** `contextvars.copy_context()` 再 `run_in_executor`
    ⇒ 它测的是**测自己的接线**，不是**生产端点的接线**
    ⇒ 把生产代码改回缺陷状态（去掉 `_ctx.run`），它**照样绿**。
    ⭐ **我把被测的那条生产路径，在测里重新实现了一遍。**
    ⇒ 判据必须**穿过真端点**，这样「生产代码怎么接线」才是被测的东西。

    ⚠️ 同样**刻意不 stub `_test_source`** —— 既有测（`tests/integration/test_v0821_admin_fetch.py`）
    每条都把它换掉，正是那个缺陷潜伏一整个版本弧的原因。此处只 stub 它**下游**的
    `is_url_allowed`（取 ctx 信号）与 `requests.head`（不出网）。

    revert-to-bad：去掉 `datasources.py` 的 `_ctx.run` ⇒ 本测红在 `seen == ["<no-ctx>"]`。
    """
    seen: list = []

    def _spy(url: str) -> bool:
        try:
            seen.append(current_tenant()["id"])
        except TenantContextError:
            seen.append("<no-ctx>")
        return True

    monkeypatch.setattr("knot.adapters.http.url_allowlist.is_url_allowed", _spy)
    import requests
    monkeypatch.setattr(requests, "head", lambda *a, **k: type("R", (), {})())

    r = client.post("/api/admin/datasources", json={
        "name": "http-src", "description": "", "db_host": "", "db_port": 0,
        "db_user": "", "db_password": "", "db_database": "", "db_type": "http",
        "http_config": '{"base_url": "https://api.example.com"}',
    }, headers=auth_headers)
    assert r.status_code == 200, r.text

    resp = client.get("/api/admin/datasources/status", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    assert seen and "<no-ctx>" not in seen, (
        f"探测线程里没有 tenant ctx（观察到 {seen!r}）\n"
        "⇒ `/status` 的 `run_in_executor` 缺 `copy_context().run`\n"
        "⇒ 后果：**所有 HTTP 数据源恒显示 \"error\"**，HTTP 200、无日志（v0.9.7 起的既有缺陷）。"
    )
    # ⭐ 顺带断**用户可见结果**：ctx 到了 ⇒ 该源不该是 "error"
    assert "error" not in resp.json().values(), (
        f"ctx 到了，但该源仍报 error：{resp.json()!r}"
    )


def test_tenant_context_error_is_not_swallowed_as_error_status(monkeypatch):
    """⭐ **租户 ctx 错误不得被伪装成「这个源连不上」**（照本仓 5 处 `reraise_if_tenant_error` 范式）。

    ⚠️ **这是本缺陷潜伏一整个弧的真正原因**：`except Exception: return "error"` 把
    「**这条路径忘了建 ctx**」这个 **bug**，变成了「**这个数据源连不上**」这个**看起来合理的业务结果**
    ⇒ 没有人会去排查一个「连不上」的数据源背后是不是上下文丢了。

    revert-to-bad：把 `_rt(e)` 去掉 ⇒ 本测红（返回 `"error"` 而不是抛）。
    """
    def _boom(url: str) -> bool:
        raise TenantContextError("模拟：线程内没有租户上下文")

    monkeypatch.setattr("knot.adapters.http.url_allowlist.is_url_allowed", _boom)
    src = {"id": 7, "db_type": "http",
           "http_config": '{"base_url": "https://api.example.com"}'}

    tok = set_active_tenant({"id": 42, "db_dir": "."})
    try:
        with pytest.raises(TenantContextError):
            ds._test_source(src)
    finally:
        reset_active_tenant(tok)
