"""闸门：平台侧审计 `platform_audit`（v0.9.8 · R-T-GATE R7）。

## 本文件最承重的一条是**原子性**
v0.9.8 草案曾把「首启审计写失败该 raise 还是吞」标为唯一影响可用性的决策；
守护者 §II 指出那个两难是**造出来的** —— 把审计 INSERT 与被记录的动作放**同一事务、单次 commit**
之后，「审计写失败」就不再是一个独立事件、与「动作失败」是**同一件事**。

⚠️ **而「拆成两次 commit」这个退化在全量里是看不见的**（守护者点名：功能都还在、测会照绿）
⇒ 判据必须能**表示那个事件**：让审计 INSERT 抛，然后断言**被记录的动作也没留下痕迹**。
   分两次 commit 的话，动作那半已经落盘 ⇒ 本测转红。

## actor 口径（别把 `whoami` 当 actor）
`'system:boot'`（启动期 seed）/ `'cli:<显式传入>'`（P2 的 CLI 强制 `--actor`）/ `None`。
⛔ 容器里 `whoami` = root/app user ⇒ 把「谁」记成 root ⇒ 本表的价值命题当场落空。
"""
from __future__ import annotations

import pytest

from knot.repositories import platform_audit_repo as par
from knot.repositories import tenant_repo


def _audit_rows(**kw) -> list[dict]:
    conn = tenant_repo.get_platform_conn()
    try:
        return par.list_recent(conn, **kw)
    finally:
        conn.close()


# ─── 原子性（must #5 —— 本文件判别力最高的一条）───────────────────────


def test_update_tenant_is_atomic_with_its_audit(tmp_db_path, monkeypatch):
    """⭐⭐ must #5：审计 INSERT 抛 ⇒ **`tenants` 的改动也不留**（同事务、单次 commit）。

    ⚠️ **这条测的存在理由 = 「拆成两次 commit」在全量里不可见**：
    功能都还在、别的测都照绿 ⇒ 那个退化会静默发生。本测的判据**能表示那个事件**。
    取材=revert：在 `update_tenant` 的 `UPDATE` 之后、审计 `insert` 之前插一个 `conn.commit()`
    → 动作那半已落盘 ⇒ 本测红（实测）。

    ⇒ 得到的性质比「审计写失败时 fail-closed」**更强**：
    **不存在「动作发生了但没记」，也不存在「记了但没发生」。**
    """
    before = tenant_repo.get_tenant(1)
    assert before is not None, "前提：fixture 已 seed tenant#1"

    def _boom(*a, **k):
        raise RuntimeError("模拟审计写失败")

    monkeypatch.setattr(par, "insert", _boom)
    with pytest.raises(RuntimeError):
        tenant_repo.update_tenant(1, name="被改过的名字", actor="cli:test")

    after = tenant_repo.get_tenant(1)
    assert after["name"] == before["name"], (
        f"审计写失败了，但 `tenants` 的改动**留下来了**（name: {before['name']!r} → {after['name']!r}）\n\n"
        "⇒ UPDATE 与审计 INSERT **不在同一个事务**里（或中间多了一次 `commit()`）。\n"
        "  那样就退回了「动作发生了但没记」这个失败模式 —— 而它正是本片刻意消掉的那个。\n"
        "  修法：两条语句用**同一个 conn**、中间**不 commit**，函数末尾**单次** `commit()`。"
    )
    assert after["updated_at"] is None or after["updated_at"] == before["updated_at"], (
        "`updated_at` 被 stamp 了但审计没写成 —— 同上，事务被拆开了")


def test_seed_emits_create_audit_in_same_transaction(tmp_db_path):
    """首启 seed ⇒ 恰一条 `platform.tenant_create`，含 slug **快照**与 `actor='system:boot'`。

    slug 冗余是刻意的：审计的价值在**事后**可读，只存 tenant_id 的话租户被删/改名后
    那条记录就退化成一个无意义的数字。
    """
    rows = _audit_rows()
    creates = [r for r in rows if r["action"] == "platform.tenant_create"]
    assert len(creates) == 1, f"seed 应恰产生 1 条 create 审计；实际 {len(creates)}（全部：{rows}）"
    r = creates[0]
    assert (r["tenant_id"], r["tenant_slug"], r["actor"]) == (1, "default", "system:boot"), r
    assert r["source"] == "startup", r


# ─── 变更审计的内容（must #2 / #3）─────────────────────────────────────


def test_update_records_before_and_after(tmp_db_path):
    """must #2：`detail` 记 before→after，且 `tenants.updated_at` 被 stamp。"""
    assert tenant_repo.update_tenant(1, status="suspended", actor="cli:kk", source="cli:test") is True
    r = _audit_rows()[0]
    assert r["action"] == "platform.tenant_update" and r["actor"] == "cli:kk", r
    assert '"from": "active"' in r["detail_json"] and '"to": "suspended"' in r["detail_json"], r
    assert tenant_repo.get_tenant(1)["updated_at"], "updated_at 未被 stamp"


def test_allowlist_change_records_that_it_changed_not_the_content(tmp_db_path):
    """⭐ must #3：`allowed_http_hosts` 的变更**只记「已变更」，不记内容**。

    ⚠️ **判据是内容级**：断言「一个确实写进去的 host 字面**不出现在** `detail_json` 里」
    ⇒ 换个写法继续记（只记第一条 / 记条目数 / 记一部分）同样会红。
    **为什么必须如此**：那份清单是部署方的**内网主机清单**（#262 同族），
    而 `GET /api/platform/audit` **会返回 `detail_json`** ⇒ 记了就等于经端点吐出去。
    取材=revert：把 `detail[k] = "changed"` 改成 `{"from":…, "to": v}` → 本测红。
    """
    secret = "internal-secret-9x.corp.local"
    tenant_repo.update_tenant(1, allowed_http_hosts=secret, actor="cli:kk")
    detail = _audit_rows()[0]["detail_json"]
    assert secret not in detail, (
        f"审计 detail 记下了 allowlist 的**内容**（泄漏 {secret!r}）：{detail}\n"
        "⇒ 那是部署方的内网主机清单，且 `GET /api/platform/audit` 会返回 detail_json。"
    )
    assert "allowed_http_hosts" in detail, f"至少要记「这个字段变过」：{detail}"


# ─── 白名单 fail-closed ───────────────────────────────────────────────


@pytest.mark.parametrize("field", ["id", "slug", "created_at", "wat"])
def test_update_rejects_fields_outside_whitelist(field, tmp_db_path):
    """白名单外字段 ⇒ `ValueError`（**不静默忽略**）。

    静默忽略会让「我改了但没生效」变成一个**无提示**的坑。
    `id` / `slug` / `created_at` 刻意不可改：前两个是身份（`slug` 还是登录链接的一部分），
    第三个是事实 ⇒ 改它们应当走一次显式评审的迁移，而不是通用写口。
    """
    with pytest.raises(ValueError, match="不接受字段"):
        tenant_repo.update_tenant(1, **{field: "x"})


def test_update_missing_tenant_returns_false_without_audit(tmp_db_path):
    """不存在的租户 ⇒ 返 False 且**不留审计**（没发生的事不该有记录）。"""
    n_before = len(_audit_rows(limit=200))
    assert tenant_repo.update_tenant(9999, name="x") is False
    assert len(_audit_rows(limit=200)) == n_before, "对不存在的租户写了审计"


# ─── ctx-free（must #4 —— 平台审计与租户审计的分野）────────────────────


def test_platform_audit_writes_without_any_tenant_ctx(tmp_db_path):
    """⭐ must #4：**无 tenant ctx 时平台审计仍可写**；同一状态下**租户审计写不了**。

    这条对比就是「平台审计为什么必须存在」的机制证据：
    - 租户审计 `audit_service.log` → `audit_repo.insert` → `get_conn` = **租户库**
      ⇒ 无 tenant ctx 时 fail-closed（`get_conn` raise）⇒ **平台动作根本没有落点**
        （这正是 v0.9.5 E2「不引入平台写操作」的理由原文）。
    - 平台审计走 `get_platform_conn()` —— **ctx-free**，正是为启动序/平台面设计的。

    ⚠️ **为什么这条测有判别力**：若哪天有人「顺手统一」把平台审计改走 `get_conn`，
    功能在**请求路径**上照常（那里有 ctx）⇒ 全量照绿，**只有启动期与 CLI 会崩**。
    本测把那个差异钉在**没有 ctx**的状态上。
    取材=injection：把 `tenant_repo.update_tenant` 里的 `get_platform_conn()` 换成
    `repositories.base.get_conn()` → 本测红（无 ctx 时 raise）。
    ⚠️ 注意注入点**不在** `platform_audit_repo` —— 它的连接是**调用方注入**的，
    模块内没有「连接来源」可改。（我第一版 docstring 写错了这个目标，实测时发现。）
    """
    from knot.core.tenant_context import (
        TenantContextError,
        clear_active_tenant,
        reset_active_tenant,
    )

    tok = clear_active_tenant()
    try:
        # ① 平台侧：无 ctx 也能写
        assert tenant_repo.update_tenant(1, name="无 ctx 也能改", actor="cli:test") is True, (
            "无 tenant ctx 时平台元数据写口失败了 —— 它必须 ctx-free"
            "（走 `get_platform_conn`，不是租户库的 `get_conn`）")
        rows = _audit_rows()
        assert rows[0]["action"] == "platform.tenant_update", rows[0]

        # ② 租户侧：同一状态下写不了（这就是平台审计必须存在的原因）
        from knot.services import audit_service
        with pytest.raises(TenantContextError):
            audit_service.log(actor=None, action="auth.login_fail", resource_type="user")
    finally:
        reset_active_tenant(tok)
