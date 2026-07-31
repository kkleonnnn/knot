"""闸门：v0.9.7 B-3 ③ —— egress allowlist 的 **per-tenant** 解析（三态 · 起源租户回退 · fail-closed）。

## 本文件守什么
`url_allowlist` 此前只读进程 env `KNOT_HTTP_ALLOWED_HOSTS` ⇒ **每个租户都继承部署方内网 API
主机的可达权**。本片把它域化到 `tenants.allowed_http_hosts`（平台库列，随 tenant ctx 搭车）。

## ⭐ 承重的那一条测是 `test_seam_real_platform_row_carries_column`
本片的**架构决策**是「载体做成 `tenants` 的一列，靠 `SELECT *` 自动进 tenant ctx」——
其余所有测都用**手工构造的 ctx 字典**，那些测**不会**证明这条接缝真的通。
⇒ 必须有一条测走**真实平台库 → `get_tenant` / `list_active_tenants` → ctx → 解析**的全链路，
否则「零分层例外」这个设计成立与否**在测里表示不出来**。

## 三态语义（判据 `is None`）—— 本文件的核心
| 租户 | 列值 | 期望 |
|---|---|---|
| 任意 | 非空串 | 该 host 集 |
| 非起源 | `None` | 空集（未配置 ⇒ 全拒绝） |
| 起源 | `None` | 回退 env |
| 任意 | `''` / `' '` / `' , '` | 空集（**已配置为空 = 部署方明确的「禁」**；起源租户**也不**回退 env） |

⚠️ **最后一行是本片唯一的 fail-open 陷阱**：写成 `if raw:` 会让 `''` / `' '` 落回 env
⇒ 「禁」被静默变成「按 env 放行」（守护者 must-fix M1）。
"""
from __future__ import annotations

import pytest

from knot.adapters.http import url_allowlist as ua
from knot.core.tenant_context import (
    clear_active_tenant,
    reset_active_tenant,
    set_active_tenant,
)

_ENV = "KNOT_HTTP_ALLOWED_HOSTS"


def _ctx(tid: int, **extra):
    """手工构造 ctx —— 镜像测侧既有的 15 处形态（`{"id":…, "db_dir":…}`）。"""
    row = {"id": tid, "db_dir": "."}
    row.update(extra)
    return set_active_tenant(row)


# ─── ⭐ 接缝（本片架构决策的唯一直接证据）──────────────────────────────


def test_seam_real_platform_row_carries_column(tmp_db_path, monkeypatch):
    """⭐⭐ 走**真实平台库**：`UPDATE` 该列 → `get_tenant` / `list_active_tenants` 的行携带它 → 解析生效。

    这条测证明的是本片的**架构决策本身**：`tenant_repo` 的两个 ctx 生产者都是 `SELECT *`
    ⇒ 加列即自动进 tenant ctx ⇒ 能力处（`executor.execute`）只读 `core.tenant_context` 就够，
    **不需要** `adapters` → `repositories` 的分层例外。

    ⚠️ 其余测都用手工 ctx 字典 ⇒ **只有这一条会因为「接缝断了」而红**
    （例如有人把 `get_tenant` 改成显式列投影 —— v0.9.5 的 `_PUBLIC_COLS` 正是那种写法，
    若哪天被推广到 `get_tenant`，per-tenant allowlist 会**静默变成「全部未配置」**）。
    取材=injection：把 `get_tenant` 的 `SELECT *` 换成不含本列的显式投影 → 本测红。
    """
    from knot.repositories import tenant_repo

    monkeypatch.delenv(_ENV, raising=False)
    conn = tenant_repo.get_platform_conn()
    conn.execute(f"UPDATE tenants SET {ua.COLUMN_NAME}=? WHERE id=1", ("seam.example.com",))
    conn.commit()
    conn.close()

    # 生产者 ①：请求路径（`resolve_tenant_by_id` → `get_tenant`）
    row = tenant_repo.get_tenant(1)
    assert ua.COLUMN_NAME in row, (
        f"`get_tenant` 返回的行不含 {ua.COLUMN_NAME!r} —— 接缝断了。\n"
        "本片的载体选择（列 + 搭 ctx 的车）依赖 `tenant_repo` 的 `SELECT *`；"
        "改成显式列投影会让 per-tenant allowlist 静默退化为「全部未配置」。"
    )
    tok = set_active_tenant(row)
    try:
        assert ua.get_allowed_hosts() == {"seam.example.com"}
        assert ua.resolve_allowed_hosts()[1] == "column"
    finally:
        reset_active_tenant(tok)

    # 生产者 ②：启动序（`list_active_tenants`）
    actives = tenant_repo.list_active_tenants()
    assert actives and ua.COLUMN_NAME in actives[0], (
        "`list_active_tenants`（启动序 ctx 生产者）返回的行不含该列 —— 启动路径接缝断了"
    )


# ─── 三态解析（must #4 · 守护者 must-fix M1）────────────────────────────


@pytest.mark.parametrize("owner,raw,expect,expect_source", [
    # ── 未配置（`None`）：起源租户回退 env；非起源租户全拒绝 ──
    (True,  None,   {"env-a.example.com", "env-b.example.com"}, "env-fallback"),
    (False, None,   set(),                                      "unconfigured"),
    # ── 已配置为空：**部署方明确的「禁」** ⇒ 全拒绝，起源租户**也不**回退 env ──
    (True,  "",     set(), "column"),
    (False, "",     set(), "column"),
    (True,  "   ",  set(), "column"),
    (False, "   ",  set(), "column"),
    (True,  " , ",  set(), "column"),
    (False, " , ",  set(), "column"),
    # ── 已配置非空：就是该集合（**不**与 env 取并/交集 —— env 里那两个不得出现）──
    (True,  "c.example.com, d.example.com", {"c.example.com", "d.example.com"}, "column"),
    (False, "c.example.com, d.example.com", {"c.example.com", "d.example.com"}, "column"),
], ids=lambda v: repr(v) if isinstance(v, str) or v is None else str(v))
def test_three_state_resolution(owner, raw, expect, expect_source, monkeypatch):
    """⭐ must #4 / M1：三态 × 起源/非起源，逐格钉死；**判据必须是 `is None`**。

    ⚠️ **6 个「已配置为空」格是本片唯一的 fail-open 陷阱**：判据一旦从 `is None` 滑成真值判断，
    「部署方明确表达的『禁』」就被静默变成「按 env 放行」。

    ⭐ **取材实测（三种似是而非的写法，红格数严格嵌套 —— 每格都有判别力，不是填充）**：

    | 把 `if raw is None:` 换成 | 红格 | 新增红的格 |
    |---|---|---|
    | `if not raw:` | **2** | `''` × 起源/非起源 |
    | `if not (raw and raw.strip()):` | **4** | + `'   '` × 2 |
    | `if not _parse(raw):` | **6** | + `' , '` × 2 |

    ⚠️ **我第一版 docstring 把这写成「`if not raw:` → 三格转红」，实测只有 2 格** ——
    因为 `'   '` 和 `' , '` 都是**真值字符串**，只有 `''` 是假值。
    ⇒ 三种空形态**各自**对应一种不同的错误写法，缺一格就有一种写法逃逸。

    最后两格额外守 R-v097-4「**永不取并集**」：env 里配了 `env-a/env-b`，
    而列配了 `c/d` ⇒ 结果必须**只有** `c/d`。
    """
    monkeypatch.setenv(_ENV, "env-a.example.com,env-b.example.com")
    extra = {} if raw is None else {ua.COLUMN_NAME: raw}
    tok = _ctx(1 if owner else 2, **extra)
    try:
        hosts, source = ua.resolve_allowed_hosts()
    finally:
        reset_active_tenant(tok)
    assert (hosts, source) == (expect, expect_source), (
        f"owner={owner} 列={raw!r} → 得到 {sorted(hosts)} / 来源={source}；"
        f"期望 {sorted(expect)} / {expect_source}\n"
        "⚠️ 若你刚把 `is None` 改成真值判断 —— 那正是 M1 点名的 fail-open："
        "`''` 是「部署方已配置为空 = 禁」，不是「未配置」。"
    )


def test_owner_null_falls_back_to_env_with_identical_host_set(monkeypatch):
    """⭐ must #3：起源租户列为 `None` ⇒ 回退 env，**host 集与 v0.9.7 之前逐字相同**。

    这是「**现网行为不变**」这个声称的唯一证据（内测服的 ConfigMap 不动即可继续工作）。
    ⚠️ 断言用**字面集合**而不是 `_parse(env)` —— 后者是拿实现比实现（重言式）；
    字面集合复刻的是 v0.9.7 **之前**那版 `get_allowed_hosts` 的语义（逗号分隔 + strip + 丢空）。
    """
    monkeypatch.setenv(_ENV, " api.example.com ,api2.example.com,, ")
    tok = _ctx(1)                                   # 起源租户 + ctx 无该键 ⇒ 未配置
    try:
        assert ua.get_allowed_hosts() == {"api.example.com", "api2.example.com"}
    finally:
        reset_active_tenant(tok)


def test_env_unset_is_deny_all_for_owner(monkeypatch):
    """secure by default 不变：起源租户未配置列 + env 也没设 ⇒ 空集 = 全拒绝。"""
    monkeypatch.delenv(_ENV, raising=False)
    tok = _ctx(1)
    try:
        assert ua.get_allowed_hosts() == set()
        assert ua.is_url_allowed("https://api.example.com/x") is False
    finally:
        reset_active_tenant(tok)


# ─── fail-closed 边界（must #10 / #11 · 守护者 must-fix M2）──────────────


def test_no_tenant_ctx_raises_not_empty_set():
    """⭐ must #10：**无 tenant ctx ⇒ 抛 `TenantContextError`**，不得静默返空集。

    两个方向都是 fail-closed（空集也拒绝），但**吞掉会掩盖「ctx 缺失」这个事实** ——
    v0.9.4 MF3 的教训就是 fail-soft 吞 `TenantContextError` 让安全记录静默丢失。
    取材=injection：给 `resolve_allowed_hosts` 包 `try/except TenantContextError: return set(), "no-ctx"`
    → 本测红。
    """
    from knot.core.tenant_context import TenantContextError

    tok = clear_active_tenant()
    try:
        with pytest.raises(TenantContextError):
            ua.get_allowed_hosts()
    finally:
        reset_active_tenant(tok)


@pytest.mark.parametrize("row", [
    {"id": 1, "db_dir": "."},                      # 测侧最常见形态
    {"id": 2, "db_dir": "tenants/2"},
    {"id": 1},                                     # `test_self_built_ctx_prefix` 的极简形态
])
def test_ctx_without_the_column_key_does_not_keyerror(row, monkeypatch):
    """⭐ must #11 / M2：ctx **缺该键**时不得 `KeyError`（取列必须 `.get()` 不得下标）。

    ctx 契约（`set_active_tenant` docstring）**只保证 `id` / `db_dir`**；测侧实测**恰 15 处**
    手工构造 ctx，**无一带本列** ⇒ 用下标会让那 15 处全部 `KeyError`。
    而 `.get()` → `None` ⇒ 非起源租户拒 / 起源租户回退 env，**两个方向都安全**。
    取材=revert：把 `.get(COLUMN_NAME)` 改成 `[COLUMN_NAME]` → 本测三格全红（且全量里另有多处红）。
    """
    monkeypatch.delenv(_ENV, raising=False)
    tok = set_active_tenant(dict(row))
    try:
        assert ua.get_allowed_hosts() == set()      # 无 env + 未配置 ⇒ 空集（不抛 KeyError）
    finally:
        reset_active_tenant(tok)


# ─── 启动期 WARN（must #13 · #262 同族）────────────────────────────────


def test_env_fallback_warn_names_env_but_never_its_value(monkeypatch, caplog):
    """⭐ must #13 / D8：起源租户回退 env 的 WARN **含 env 名、不含 env 值、不枚举 host**。

    #262 的修法原文是「只报 env 名，绝不报 env 值」，且该规则对**日志**同样成立。
    本测是 v0.9.7 之后 #262 端到端守护的**新落点**（旧落点在 env 模式里，本片已退役该模式）。
    取材=revert：把 WARN 改成回显 `os.environ.get(ENV_NAME)` 或 `sorted(hosts)` → 本测红。
    """
    import logging

    secret_host = "internal-secret-9x.corp.local"
    monkeypatch.setenv(_ENV, secret_host)
    caplog.set_level(logging.WARNING, logger=ua.__name__)
    ua.warn_if_owner_using_env_fallback({"id": 1, "db_dir": ".", ua.COLUMN_NAME: None})
    # ⚠️ 断 **record 的 message 本体**，不用 `caplog.text` —— 后者含 pytest 拼的日志头
    # （`url_allowlist.py:177`），里面的**行号自带数字** ⇒ 下面那条「不得含数字」的断言会打在行号上。
    # （实施期实测踩到：这正是 §4.4 记的「v0.9.6 `:312` 的 `isdigit` 断言不能照搬」的同族。）
    assert caplog.records, "WARN 没打出来（logger 名或 level 不对？）"
    text = "\n".join(r.getMessage() for r in caplog.records)

    assert ua.ENV_NAME in text, f"WARN 未点名 env（运维无从下手）：{text!r}"
    assert ua.COLUMN_NAME in text, f"WARN 未点名该迁往哪个列：{text!r}"
    assert secret_host not in text, (
        f"WARN 泄漏了 env **值**（{secret_host!r}）——#262 的规则是只报名不报值，日志同样适用：{text!r}"
    )
    # ⚠️ 连**条目数**都不打：Stage 1' 的 D11 原写「记条目数」，被 #262 AST 哨兵拦下 ——
    # `len(os.environ...)` 在污点传播上仍是 env 派生值。选「不打」而非「加 `_ALLOWED` 例外」，
    # 因为例外按 (文件, **变量名**) 放行会让本文件将来任何同名变量静默获得豁免 = 弱化哨兵。
    assert not any(ch.isdigit() for ch in text), (
        f"WARN 含数字 —— 可能又开始回显 env 派生的量（条目数/长度）：{text!r}"
    )


def test_warn_is_silent_when_column_configured():
    """已迁移到列 ⇒ WARN **静默**（否则每次启动都喊、运维会学会忽略它）。"""
    import logging

    import knot.adapters.http.url_allowlist as mod
    records: list = []
    handler = logging.Handler()
    handler.emit = records.append
    mod._logger.addHandler(handler)
    try:
        mod.warn_if_owner_using_env_fallback({"id": 1, mod.COLUMN_NAME: "x.example.com"})
    finally:
        mod._logger.removeHandler(handler)
    assert not records, f"列已配置却仍 WARN：{[r.getMessage() for r in records]}"


# ─── 永不取并集（must #9 · R-v097-4）──────────────────────────────────


def test_never_unions_across_tenants(monkeypatch):
    """⭐ must #9 / R-v097-4：两租户的 allowlist **互不可见** —— 既不取并集也不取交集。

    为什么这条要单独存在（参数化测里已有一格顺带守了）：**「顺手 union」是个很自然的重构** ——
    「起源租户的 env 是部署方给的底线，所有租户都该能访问吧？」听起来合理，实则反了：
    env 是**起源租户自己的** allowlist，把它并进客租户 = 客租户获得部署方内网可达权（本片要治的病）；
    反过来把客租户的列并进 env 侧 = **为给客租户开权而放宽起源租户**（守护者确认「交集是反向的」）。
    取材=injection：把 `resolve_allowed_hosts` 的 column 分支改成
    `_parse(raw) | _parse(os.environ.get(ENV_NAME, ""))` → 本测红。
    """
    owner_only = "owner-only.corp.local"
    guest_only = "guest-only.corp.local"
    monkeypatch.setenv(_ENV, owner_only)

    tok = _ctx(2, **{ua.COLUMN_NAME: guest_only})       # 非起源租户：只配了自己的
    try:
        guest = ua.get_allowed_hosts()
    finally:
        reset_active_tenant(tok)
    tok = _ctx(1)                                        # 起源租户：未配置 ⇒ 回退 env
    try:
        owner = ua.get_allowed_hosts()
    finally:
        reset_active_tenant(tok)

    assert guest == {guest_only}, f"客租户看见了不属于它的 host：{sorted(guest)}"
    assert owner == {owner_only}, f"起源租户的集合被污染：{sorted(owner)}"
    assert not (guest & owner), f"两租户 allowlist 出现交集：{sorted(guest & owner)}"


# ─── 写侧 + 探测侧（must #7 / #8 · D6 —— 经同一 choke point 自动跟随，但必须实证）──

#: 与生产调用点分工：**端点 → `_assert_http_base_url_allowed` 的接线**已由
#: `tests/integration/test_closeout_19b.py:25`（v0.8.20 F4）覆盖（env 口径的 400）。
#: 本节补的是**「同一个 host 在不同租户下结果相反」**这一层 —— 那是 v0.9.7 新引入的性质。


def _http_source(base_url: str) -> dict:
    import json
    return {"db_type": "http", "http_config": json.dumps({"base_url": base_url})}


def test_write_side_is_per_tenant(monkeypatch):
    """⭐ must #7 / D6：写侧（存数据源前的校验）**同一 host、两租户、结果相反**。

    `datasources._assert_http_base_url_allowed` 经 `is_url_allowed` → `get_allowed_hosts`
    ⇒ D4 的「零改动自动跟随」。**但「自动跟随」是声称，不是实证** —— 本测就是实证。
    取材=revert：把 `_assert_http_base_url_allowed` 里的 `is_url_allowed(base_url)` 换成
    直接读 env（绕开租户解析）→ 本测的「非起源租户应 400」那半转绿失败（即本测红）。
    """
    from fastapi import HTTPException

    from knot.api.admin import datasources as ds

    host = "deployment-internal.corp.local"
    monkeypatch.setenv(_ENV, host)                       # 只在**起源租户**的 allowlist 里

    tok = _ctx(1)                                        # 起源租户 ⇒ 放行（不抛）
    try:
        ds._assert_http_base_url_allowed("http", _http_source(f"https://{host}")["http_config"])
    finally:
        reset_active_tenant(tok)

    tok = _ctx(2)                                        # 非起源租户 ⇒ 400
    try:
        # ⚠️ 用 `try/except/else` 而非 `pytest.raises` —— 真实的失败模式（写侧不再按租户判断）
        # 只会得到裸的 `DID NOT RAISE HTTPException`，**不说明这意味着什么**。
        # （守护者 v0.9.6 Stage 4 §II：**消息要挂在事情真的出错的那一行**；这是同族第 5 次。）
        try:
            ds._assert_http_base_url_allowed("http", _http_source(f"https://{host}")["http_config"])
        except HTTPException as e:
            assert e.status_code == 400, f"应 400，实际 {e.status_code}"
            assert "KNOT_" not in str(e.detail), (
                f"写侧 400 的 detail 点名了 env（allowlist 已 per-tenant ⇒ 误导）：{e.detail!r}")
        else:
            pytest.fail(
                f"非起源租户存 {host!r} **未被拒绝** —— 写侧 allowlist 不再按租户判断。\n"
                "该 host 只在**起源租户**的 allowlist（env）里；非起源租户存得进去，意味着它可以\n"
                "把部署方内网主机写进自己的数据源，之后每次列表加载还会被 HEAD 探测一次\n"
                "（v0.8.20 F4 修过的那条缝在多租户下复发）。\n"
                "⇒ 检查 `_assert_http_base_url_allowed` 是否还在走 `is_url_allowed`（经 tenant ctx），"
                "而不是自己直接读 env。"
            )
    finally:
        reset_active_tenant(tok)


def test_probe_side_is_per_tenant_and_does_not_reach_network(no_network, monkeypatch):
    """⭐ must #8 / D6：探测侧（列表页的健康探测）也按租户 —— 非起源租户**连 HEAD 都不发**。

    这条缝的原始形态（v0.8.20 F4 修的）：HEAD 探测**绕过** allowlist ⇒ 存进去的内网 base_url
    **每次列表加载都被探测一次**。per-tenant 化后必须保持：非本租户 allowlist 内的 host 不探测。

    ⚠️ **oracle 是「有没有真发请求」，不是返回值** —— `_test_source` 的 `except Exception:
    return "error"` 会把任何异常折成 `"error"`，所以「返回 error」在两种情形下都成立
    （没探测 vs 探测了但失败）⇒ **返回值分不清这两件事**。用出网探针的**记录列表**才分得清。
    （同一个判据形状：v0.9.6 的 no_network 从「只抛」改成「先记录再抛」正是为此。）
    """
    host = "deployment-internal.corp.local"
    monkeypatch.setenv(_ENV, host)
    src = _http_source(f"https://{host}")

    from knot.api.admin import datasources as ds

    tok = _ctx(2)                                        # 非起源租户 ⇒ 不该发请求
    try:
        assert ds._test_source(src) == "error"
    finally:
        reset_active_tenant(tok)
    assert no_network == [], (
        f"非起源租户的 host 仍被 HEAD 探测了：{no_network}\n"
        "⇒ v0.8.20 F4 修的那条缝（探测绕过 allowlist）在多租户下复发。"
    )

    tok = _ctx(1)                                        # **正对照**：起源租户应真的去探测
    try:
        ds._test_source(src)
    finally:
        reset_active_tenant(tok)
    assert no_network, (
        "起源租户的 host 也没被探测 —— 说明门变成了「谁都不探测」= 把功能删掉，"
        "而不是「按租户判断」。（没有这半，上半可以靠『全拒绝』通过。）"
    )


# ─── public 名不得被顺手删（§8.4）──────────────────────────────────────


def test_public_names_still_exported():
    """`knot.adapters.http.__init__` re-export 的三个名仍在（签名不变是 D4 杠杆的前提）。"""
    from knot.adapters import http as pkg

    for name in ("check_url_allowed", "get_allowed_hosts", "is_url_allowed"):
        assert hasattr(pkg, name), f"`knot.adapters.http` 少了 re-export 的 {name!r}"
