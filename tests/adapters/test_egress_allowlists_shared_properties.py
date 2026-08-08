"""两份 egress allowlist 共用**一张性质表**，且表的管辖集**从列名派生**（v0.9.18 P-a）。

⭐ **为什么不给 webhook 照抄一份 v0.9.7 的测**（kk 2026-08-07 的判据用在测上）：
`tests/adapters/test_http_egress_per_tenant.py` 已把三态语义钉得很细。
若本片再复制一份**结构相同、只换了模块名**的文件，就得到了**第二份会漂的清单** ——
两份将来必然分头演进，而**分头演进的那一刻不会有人报错**。

⇒ 本模块只做一件事：**把「每份 allowlist 都必须成立的性质」写一次，参数化跑遍所有 allowlist。**
而「所有 allowlist」不是手写的 —— 它由 `_MUTABLE_TENANT_FIELDS` 里的 `allowed_*` 列派生
（与 `tests/test_allowlist_column_registration.py` 同一个真相源）。

⇒ **第三份 allowlist 落地时，会被自动拉进这张表**；若它没有登记 resolver，
`test_every_managed_column_has_a_registered_resolver` 直接红。
⇒ 「新增一份 allowlist 却没人测它的三态」这件事，从此**不可能静默发生**。

⚠️ **本模块不替代** v0.9.7 那份 —— 那里还有 http 特有的项（接缝测 / WARN 行为 / 跨租户不取并集）。
本模块只管**共有性质**。
"""
from __future__ import annotations

import pytest

from knot.adapters.http import url_allowlist as ua
from knot.adapters.notification import webhook as wh
from knot.core.tenant_context import OWNER_TENANT_ID, reset_active_tenant, set_active_tenant
from knot.repositories import tenant_repo

#: 列名 → 该列的 resolver 模块。**唯一的手写映射**，且由下面第一条测强制它覆盖所有管辖列。
#: ⚠️ 刻意手写这一处：「哪个模块负责哪一列」是真实的设计信息，无法从别处派生；
#:    但**它是否完整**可以被检验 —— 那就够了（可检验的手写 ≠ 会漂的清单）。
_RESOLVERS = {
    "allowed_http_hosts": ua,
    "allowed_webhook_hosts": wh,
}

_MANAGED = tuple(f for f in tenant_repo._MUTABLE_TENANT_FIELDS if f.startswith("allowed_"))


def _ctx(tid: int, **extra):
    """手工构造 ctx —— 镜像测侧既有形态（`{"id":…, "db_dir":…}`，**不带** allowlist 列）。"""
    row = {"id": tid, "db_dir": "."}
    row.update(extra)
    return set_active_tenant(row)


def _resolve(mod) -> tuple[set[str], str]:
    """取该模块的 `(hosts, source)` resolver。

    ⭐ **两个模块刻意用同一个函数名** `resolve_allowed_hosts` —— 同一种能力就该同一个名字。
    （初版 webhook 侧叫 `resolve_webhook_allowed_hosts`，于是这里要 `getattr` 兜差异；
    ruff B009 报出来后才发现：**要兜的差异本身就不该存在**。）
    """
    return mod.resolve_allowed_hosts()


def test_every_managed_column_has_a_registered_resolver():
    """⭐ 新增一份 allowlist 却不登记 resolver ⇒ 本测红 ⇒ 它不会绕过下面那张性质表。

    revert-to-bad：往 `_MUTABLE_TENANT_FIELDS` 加一个 `allowed_xxx` 而不加进 `_RESOLVERS` ⇒ 红。
    """
    assert _MANAGED, "管辖集为空 —— 对空集做「每个都…」的断言恒真（五问③）"
    missing = [c for c in _MANAGED if c not in _RESOLVERS]
    assert not missing, (
        f"这些 allowlist 列没有登记 resolver：{missing}\n"
        "⇒ 它们的三态语义**没有任何测覆盖**，而本模块的性质表也跑不到它们。"
    )


@pytest.mark.parametrize("column", _MANAGED)
@pytest.mark.parametrize(
    "owner,raw,expect_source",
    [
        # ── NULL = 未配置 ──
        (True, None, "env-fallback"),      # 起源租户 ⇒ 回退 env
        (False, None, "unconfigured"),     # 非起源租户 ⇒ 全拒绝
        # ── '' / 空白 = 部署方**明确表达的「禁」** ⇒ 全拒且**不回退**（唯一的 fail-open 陷阱）──
        (True, "", "column"),
        (False, "", "column"),
        (True, "   ", "column"),
        (True, " , ", "column"),
        # ── 非空 = 该集合本身 ──
        (True, "c.example.com", "column"),
        (False, "c.example.com", "column"),
    ],
    ids=lambda v: repr(v) if isinstance(v, str) or v is None else str(v),
)
def test_three_state_source_is_identical_across_allowlists(column, owner, raw, expect_source, monkeypatch):
    """⭐ **三态的「来源」判定在每份 allowlist 上必须逐格一致**。

    ⚠️ **为什么断言 `source` 而不只是 host 集合**：`source` 是判据**走了哪条分支**的直接证据。
    只断集合的话，「`''` 落回 env 而 env 恰好为空」与「`''` 正确地拒绝」**得到同一个空集**
    ⇒ 那个 fail-open 在集合级 oracle 里**表示不出来**（本仓五问②的形状）。

    ⚠️ 6 个「已配置为空」格是唯一的 fail-open 陷阱：判据一旦从 `is None` 滑成真值判断，
    「明确的禁」就静默变成「按 env 放行」。
    """
    mod = _RESOLVERS[column]
    monkeypatch.setenv(mod.ENV_NAME, "env-only.example.com")
    tid = OWNER_TENANT_ID if owner else OWNER_TENANT_ID + 1
    tok = _ctx(tid, **({column: raw} if raw is not None else {}))
    try:
        hosts, source = _resolve(mod)
        assert source == expect_source, (
            f"[{column}] owner={owner} raw={raw!r} ⇒ 来源应为 {expect_source!r}，实际 {source!r}"
        )
        # ⭐ 无条件加断一条内容级性质：**env 里那个 host 只允许在 env-fallback 时出现**
        if source != "env-fallback":
            assert "env-only.example.com" not in hosts, (
                f"[{column}] source={source} 却带上了 env 里的 host ⇒ 与 env 取了并集/回退了"
            )
    finally:
        reset_active_tenant(tok)


@pytest.mark.parametrize("column", _MANAGED)
def test_ctx_without_the_column_key_does_not_keyerror(column):
    """⭐ v0.9.7 must-fix **M2**：ctx 契约只保证 `id`/`db_dir` ⇒ 取值必须 `.get()` 不得下标。

    实测 `set_active_tenant(` 全仓 **128 处 / 15 文件**，含 conftest 的 **autouse** 行
    （只有 `{id,slug,name,status,db_dir}`）⇒ 下标会炸一大片。
    revert-to-bad：把 `.get(COLUMN_NAME)` 改成 `[COLUMN_NAME]` ⇒ 本测红（`KeyError`）。
    """
    mod = _RESOLVERS[column]
    tok = _ctx(OWNER_TENANT_ID + 1)          # 非起源 + 无该列 ⇒ 应当干净地拒绝
    try:
        hosts, source = _resolve(mod)
        assert (hosts, source) == (set(), "unconfigured"), f"[{column}] 缺列时未 fail-closed：{hosts}/{source}"
    finally:
        reset_active_tenant(tok)


@pytest.mark.parametrize("column", _MANAGED)
def test_no_tenant_ctx_raises_rather_than_returning_empty_set(column):
    """⭐ 无 ctx 必须 **raise**，不得静默返空集。

    ⚠️ 「返空集」看起来也是 fail-closed，但它**把 bug 变成了静默的功能缺失** ——
    而 raise 会响亮地指出「这条路径忘了建租户上下文」。（OOS-1v2：无 ctx → raise，严禁全局回退。）
    """
    from knot.core.tenant_context import TenantContextError, clear_active_tenant

    mod = _RESOLVERS[column]
    tok = clear_active_tenant()
    try:
        with pytest.raises(TenantContextError):
            _resolve(mod)
    finally:
        reset_active_tenant(tok)


@pytest.mark.parametrize("column", _MANAGED)
def test_every_allowlist_has_a_startup_env_fallback_warn(column):
    """⭐ 每份 allowlist 都必须有**同一种**启动 WARN，且**接线进启动序**（v0.9.18 P-a 补漏）。

    ⚠️ **为什么这条测存在**：`url_allowlist` v0.9.7 就有这个 WARN，而 webhook 那份**漏了** ——
    正是「同类物没被一起处理」的又一实例。⇒ 把它变成派生断言，第三份 allowlist 也逃不掉。

    ⭐ **它守的不只是代码整齐**：`KNOT_WEBHOOK_ALLOWED_HOSTS` 从未写进 DEPLOY/README
    ⇒ 「现网配没配」只能靠集群权限去查，而**启动日志有没有这一行就是答案**
    ⇒ 这条 WARN 是**没有运维权限的人唯一的观测口**。删了它，那个问题就再也答不了。

    revert-to-bad：删掉 `webhook.warn_if_owner_using_env_fallback` 或它在 `main.py` 的接线 ⇒ 本测红。
    """
    import ast
    import pathlib as _p

    mod = _RESOLVERS[column]
    assert hasattr(mod, "warn_if_owner_using_env_fallback"), (
        f"[{column}] 该 allowlist 模块没有启动期 env-fallback WARN —— "
        "运维将无法知道「现网配没配」（那需要集群权限）。"
    )
    # ⚠️ 光有函数不够 —— 必须**真的接进启动序**（否则它永远不响；v0.9.16 那条哑掉的 WARN 同形）
    src = (_p.Path(__file__).resolve().parents[2] / "knot/main.py").read_text(encoding="utf-8")
    called = {
        n.func.attr
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "warn_if_owner_using_env_fallback" in called, (
        "`main.py` 启动序里没有任何 `warn_if_owner_using_env_fallback(...)` 调用 —— WARN 永不会响"
    )
    # 且**每份** allowlist 各自被调一次（两份共用一个函数名 ⇒ 数调用次数）
    n_calls = sum(
        1 for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "warn_if_owner_using_env_fallback"
    )
    assert n_calls >= len(_MANAGED), (
        f"启动序里只有 {n_calls} 处 env-fallback WARN 调用，但有 {len(_MANAGED)} 份 allowlist "
        f"⇒ 至少有一份的 WARN 没接线（它会静默地永不响）。"
    )
