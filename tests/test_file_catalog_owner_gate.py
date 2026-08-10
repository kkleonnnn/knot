"""闸门：per-tenant 隔离在 HTTP 数据面上的三处落点（v0.9.6 ① + **v0.9.7 ②③**）。

## 本文件承重的原因不变
既有套件里触及 `pick_http_route` / `execute` / `run_http_step` 的 **8 个测文件全部在 tid=1（起源租户）
下跑**（显式 `{1,}` 或经 `conftest` autouse `{"id": 1, …}`，实读）⇒ **起源租户路径覆盖充分，
非起源租户路径零覆盖**。本文件补的就是那一半。

## ⭐ v0.9.7 的语义反转（读本文件前必须先读这段）
v0.9.6 靠**「是不是起源租户」**这一个谓词挡住三处；其中**两处是代偿控制**，随 ②③ 落地已摘：

| 落点 | v0.9.6 | v0.9.7 | 谁在守 |
|---|---|---|---|
| `catalog_loaders.load_file_layer` | 非起源租户返完整 empty 五元组 | **不变** | ① file 层只归起源租户 |
| `http_planner.pick_http_route` Layer 0 | 非起源租户不做 HTTP 路由 | **已摘** | 改由「spec 有没有绑本租户数据源」判（②） |
| `executor.execute` owner 门 | 非起源租户 → `HTTPAuthError` | **已摘** | 改由 ②（`source_id`）+ ③（`allowed_http_hosts`）判 |

⇒ **按租户区分的不再是「是不是起源租户」，而是「凭据是不是自己的」+「主机是不是自己 allowlist 里的」。**
路由命中、执行被 allowlist 拒 = **预期行为**（不是缺陷）；「非起源租户一律拒」才是缺陷
（那是把功能删掉 —— 故本文件有 `test_non_owner_with_its_own_allowlist_is_allowed` 作正对照）。

## 能力处 vs 决策处（这个分工没变，是本文件的骨架）
- **能力处** = `executor.execute`：唯一发网络请求的函数。两道**独立**硬边界 ——
  ② 无 `source_id` → 拒；③ host 不在本租户 allowlist → 拒。**绕不过。**
- **决策处** = `pick_http_route`：无 `source_id` → 软降级落 SQL **+ 记日志**（不记 = v0.7.29b 静默落 SQL）。
  ⚠️ 它**可以被绕过**：`run_http_step` 是公开函数、自带 spec、不重新求 route
  ⇒ 故两道门必须在能力处独立成立（`test_direct_run_http_step_is_refused_by_both_gates`）。

⭐ 这个分工是评审三轮才收敛的（门装错位置错了两次）：v1 论证在「谁 import `execute`」= **拓扑** ·
v2 门在 `pick_http_route` = **决策点** · v3 才落到 `execute` = **能力行使处**。
**门要装在能力被行使的那一行。**

## ⚠️ 写本文件的测时最容易踩的两个「测不到它想测的地方」
1. **spec 必须带 `source_id`**（`_evil_tables(sid)`）：否则会被 **② 的门**拦住，
   「③ 拦住了它」这件事根本没被验到。实测：摘门后旧版无 `source_id` 的恶意表**照绿**。
2. **ctx 必须从真实平台库行建**（`_in_real`）：`_in()` 是手工字典、**不含平台列**
   ⇒ `allowed_http_hosts` 永远读成「未配置」，无论你怎么 UPDATE 那一列。
"""
from __future__ import annotations

import ast
import asyncio
import json
import pathlib

import pytest

from knot.adapters.http import url_allowlist as ua_mod
from knot.core.tenant_context import (
    OWNER_TENANT_ID,
    current_tenant,
    is_owner_tenant,
    reset_active_tenant,
    set_active_tenant,
)
from knot.services.agents import catalog, catalog_loaders, catalog_state

_REPO = pathlib.Path(__file__).resolve().parents[1]

#: 恶意 host（**任何租户的 allowlist 都不含它** —— 除了显式配上去的正对照测）
_EVIL_HOST = "attacker.example.com"

#: 恶意 http 表 + lexicon —— 租户 admin 经 `PUT /api/admin/catalog` 能写的全部东西
#: （`api/catalog.py:69-76` 对 `tables` **只校验 `isinstance(v, list)`**，`source_type`/`http_spec` 零校验）
#:
#: ⭐ **v0.9.7 必须带 `source_id`**（否则本文件多条测会**因为错误的原因而绿**）：
#: commit 8 起 `pick_http_route` 对**无 `source_id`** 的 spec 一律软降级 ⇒ 不带 source_id 的恶意表
#: 会被 **② 的门**拦住，于是「③ 的 per-tenant allowlist 拦住了它」这件事**在测里根本没被验到**。
#: 实测坐实：摘掉 v0.9.6 owner 门后，旧版 `_EVIL_TABLES`（无 source_id）那两条测**照绿**。
#: ⇒ 带上 source_id = 让 ② 满足、把判别力交给 ③。
def _evil_tables(source_id: int) -> list:
    return [{
        "db": "evil", "table": "exfil", "columns": [],
        "source_type": "http",
        "http_spec": {"method": "GET", "url_template": "{base_url}/v1/all", "source_id": source_id},
    }]


#: 无 `source_id` 的形态 —— 专测 ②（凭据未绑本租户数据源）
_UNBOUND_TABLES = [{
    "db": "evil", "table": "exfil", "columns": [],
    "source_type": "http",
    "http_spec": {"method": "GET", "url_template": "{base_url}/v1/all",
                  "base_url": f"https://{_EVIL_HOST}", "auth_header": "k", "auth_value": "v"},
}]
_EVIL_LEXICON = {"持仓": ["evil.exfil"]}


def _plant_evil_http_source(tid: int, dbdir: str, host: str = _EVIL_HOST) -> int:
    """在该租户库里**直接经 repo** 种一条指向 `host` 的 http 数据源，返回其 id。

    ⚠️ **为什么绕过 API 写侧门**：③ 落地后 `POST/PUT /api/admin/datasources` 会对
    「host 不在**本租户** allowlist」返 400 ⇒ 经 API 根本存不进来。
    但**读侧的门必须独立成立**（防御纵深）：存量行、部署方直接 UPDATE、或哪天写侧门被绕，
    执行处都必须仍然拒。⇒ 本 helper 制造的正是「库里已经有一条坏行」这个前提。
    """
    import json as _json

    from knot.repositories import data_source_repo, user_repo
    tok = _in(tid, dbdir)
    try:
        admin = user_repo.get_user_by_username("admin")
        return data_source_repo.create_datasource(
            (admin or {}).get("id", 1), f"evil-http-{tid}", "读侧门测试用（绕过 API 写侧门）",
            "", 0, "", "", "", db_type="http",
            http_config=_json.dumps({"base_url": f"https://{host}",
                                     "auth_header": "k", "auth_value": "v"}),
        )
    finally:
        reset_active_tenant(tok)


def _observed_source_labels() -> set[str]:
    """把 `resolve_allowed_hosts` 的**来源标签**从行为派生出来（不硬编字面）。

    ⚠️ **为什么派生而不是硬编三个字面**：硬编的清单在本仓已被反复证明会漂
    （加第四个标签时没人会想起来同步测里那份）。这里跑遍三态、收集实际返回的标签
    ⇒ 将来加标签只要有一个状态能产生它，就自动被下面的守护覆盖。
    ⚠️ 配一条**防空转**的前提断言（见调用点）：若派生出空集，下面的 for 循环会静默通过
    —— 那正是「绿分不清『守住了』与『探针没到达』」。
    """
    seen = set()
    for row in ({"id": 2, "db_dir": "."},                                   # 非起源 + 未配置
                {"id": OWNER_TENANT_ID, "db_dir": "."},                      # 起源 + 未配置 → env 回退
                {"id": 2, "db_dir": ".", ua_mod.COLUMN_NAME: "x.example.com"}):  # 已配置
        tok = set_active_tenant(row)
        try:
            seen.add(ua_mod.resolve_allowed_hosts()[1])
        finally:
            reset_active_tenant(tok)
    return seen


def _set_allowlist(tid: int, value: str | None) -> None:
    """设某租户的 `tenants.allowed_http_hosts`（部署方动作 —— 无端点，唯一途径就是直接 UPDATE）。"""
    from knot.repositories import tenant_repo
    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET allowed_http_hosts=? WHERE id=?", (value, tid))
    conn.commit()
    conn.close()


@pytest.fixture
def two_tenants(tmp_path, monkeypatch):
    """tmp 数据根 + 两租户库（tid 1 = owner / tid 2 = 非 owner），各自建表。"""
    from knot.repositories import base, tenant_repo
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir="tenants/1")
    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()
    for tid, dbdir in ((1, "tenants/1"), (2, "tenants/2")):
        tok = set_active_tenant({"id": tid, "db_dir": dbdir})
        try:
            base.init_db()
        finally:
            reset_active_tenant(tok)
    catalog_state.invalidate_all()
    return {1: "tenants/1", 2: "tenants/2"}


def _in(tid: int, dbdir: str):
    return set_active_tenant({"id": tid, "db_dir": dbdir})


def _in_real(tid: int):
    """从**真实平台库行**建 ctx —— 生产就是这么建的（`get_tenant` → `set_active_tenant`）。

    ⚠️ **测 `tenants.allowed_http_hosts` 必须用这个，不能用 `_in()`**（实施期实测踩到）：
    `_in()` 建的是**手工字典** `{"id":…, "db_dir":…}`，**不含平台列** ⇒ `resolve_allowed_hosts`
    永远走到「未配置」分支 ⇒ 无论你怎么 UPDATE 那一列，测都在验「未配置」这一种情形。
    实测症状：日志 `allowlist 来源=unconfigured`，而我以为在验「显式配空」/「配了本 host」。
    ⇒ 又一次「测没到达它想测的地方」。
    """
    from knot.repositories import tenant_repo
    row = tenant_repo.get_tenant(tid)
    assert row is not None, f"tenant#{tid} 不存在 —— fixture 没建好"
    return set_active_tenant(row)


# `no_network` fixture 已于 v0.9.7 提到 `tests/conftest.py`（第二个消费者出现 ⇒ 不复制判据）。


# ─── 谓词本身（验收 4/5/6）──────────────────────────────────────────────


def test_no_tenant_ctx_is_fail_closed():
    """验收 4：无 tenant ctx 调谓词 → **raise**（fail-closed 且响亮），不得静默返 False。

    静默返 False 会让「无 ctx」被当成「非 owner」⇒ 启动/脚本路径悄悄丢掉 file 层。
    取材=injection：把 `is_owner_tenant` 改成 `try/except: return False` → 本测红。
    """
    from knot.core.tenant_context import TenantContextError, clear_active_tenant
    tok = clear_active_tenant()
    try:
        with pytest.raises(TenantContextError):
            is_owner_tenant()
    finally:
        reset_active_tenant(tok)


@pytest.mark.parametrize("tid,expect", [
    (1, True),
    (2, False),
    (True, False),      # ⭐ bool 是 int 子类且 `True == 1`
    (1.0, False),       # ⭐ `1.0 == 1`
    ("1", False),
    (None, False),
])
def test_owner_predicate_is_strict_int(tid, expect):
    """⭐ 验收 5：`type(tid) is int and tid == OWNER_TENANT_ID` —— 严格 int。

    接 v0.9.4 的 tid 严格化教训：宽松比较会把 `True` / `1.0` 当成 owner
    ⇒ 一个来自 JSON 的 `1.0` 或一个 `True` 就能拿到部署方的 file 层。
    取材=injection：改成 `tid == OWNER_TENANT_ID`（去掉类型判定）→ `True` / `1.0` 两格红。
    """
    tok = set_active_tenant({"id": tid, "db_dir": "."})
    try:
        assert is_owner_tenant() is expect
    finally:
        reset_active_tenant(tok)


def test_owner_tenant_id_is_pinned_behaviorally(tmp_path, monkeypatch):
    """⭐ 验收 6：**行为式**钉住 —— seed 空平台库后读回的租户 id **== 常量**。

    ⚠️ **刻意不写 `assert OWNER_TENANT_ID == 1`** —— 那只是复述常量（tautology）。
    这里断言的是「**`seed_default_tenant` 造出来的那个租户，就是常量指的那个**」
    ⇒ 若将来 seed 改成别的 id 而常量没跟着改，本测红。
    """
    from knot.repositories import tenant_repo
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(tmp_path / "knot.db"))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir="tenants/1")
    rows = tenant_repo.list_tenants()
    assert len(rows) == 1, f"seed 应恰造 1 个租户；实际 {rows}"
    assert rows[0]["id"] == OWNER_TENANT_ID, (
        f"seed 造出的租户 id={rows[0]['id']}，而 `OWNER_TENANT_ID`={OWNER_TENANT_ID} —— "
        "两者必须一致：常量的语义是「多租户之前就存在的那个租户」"
    )


# ─── 文件闸（验收 2/3）─────────────────────────────────────────────────


def test_non_owner_file_layer_is_fully_empty(two_tenants):
    """⭐ 验收 2：非 owner 的 file 五元组恰 `({}, [], "", [], "empty")` —— **禁半空**。

    「禁半空」的理由是具体的（实读 `catalog.reload()` 的五种合并策略）：
    `business_rules = db_rules if db_rules.strip() else f_rules` ⇒ 只清 tables 而留 `f_rules`，
    **空-DB 的非 owner 仍会拿到部署方业务口径**；`lexicon` 更是**无条件合并**。
    取材=revert：让 `load_file_layer` 直接 `return _load_from_files()` → 本测红。
    """
    tok = _in(2, "tenants/2")
    try:
        assert catalog_loaders.load_file_layer() == ({}, [], "", [], "empty")
    finally:
        reset_active_tenant(tok)


def test_owner_file_layer_is_unchanged(two_tenants):
    """**正对照**：owner 侧仍拿到真 file 层（与 `_load_from_files()` 逐字相同）。

    没有这一条，上一条测可以靠「让所有人都空」来通过 —— 那是把功能删掉而不是加门。
    """
    tok = _in(1, "tenants/1")
    try:
        assert catalog_loaders.load_file_layer() == catalog_loaders._load_from_files()
    finally:
        reset_active_tenant(tok)


def test_non_owner_reload_strict_does_not_raise(two_tenants):
    """验收 3：非 owner 下 `reload(strict=True)` **不抛**、`source='empty'`。

    承重：`strict=True` 是 admin reload 与 `pick_http_route` 触发路径用的 ——
    若它抛，非 owner 租户的 admin 面/查询面会 5xx 而不是优雅降级。
    """
    tok = _in(2, "tenants/2")
    try:
        catalog_state.invalidate_all()
        catalog.reload(strict=True)
        st = catalog_state.get_state()
        assert (st["tables"], st["lexicon"], st["business_rules"], st["source"]) == ([], {}, "", "empty")
    finally:
        reset_active_tenant(tok)


# ─── 软降级 + 硬边界（验收 7 / 7b / 8）──────────────────────────────────


def _write_evil(tid: int, dbdir: str, tables: list | None = None):
    """把恶意表 + lexicon 写进该租户库的 catalog。`tables=None` → 无绑定形态（测 ②）。"""
    from knot.repositories import catalog_repo
    tok = _in(tid, dbdir)
    try:
        catalog_repo.update_catalog(
            1, tables=json.dumps(tables if tables is not None else _UNBOUND_TABLES,
                                 ensure_ascii=False),
            lexicon=json.dumps(_EVIL_LEXICON, ensure_ascii=False))
    finally:
        reset_active_tenant(tok)
    catalog_state.invalidate_all()


def test_malicious_db_http_table_is_refused_by_per_tenant_allowlist(two_tenants, no_network):
    """⭐⭐ **v0.9.7 语义反转**：恶意 DB http 表现在**会被路由**（② 满足），由 **③ 的 per-tenant
    allowlist** 在执行处拒 + **零出网**。

    ## 反转前后
    v0.9.6：`pick_http_route` 的 **Layer 0**「非起源租户不做 HTTP 路由」把它挡在路由阶段
    ⇒ 本测原名 `..._is_not_routed_for_non_owner`。
    v0.9.7 摘掉 Layer 0（它是 ②③ 未落地期间的代偿控制）⇒ **按租户区分的不再是「是不是起源租户」，
    而是「凭据是不是自己的」（②）+「主机是不是自己 allowlist 里的」（③）**。
    ⇒ 路由**应当**命中（这是功能，不是缺陷），拒绝**应当**发生在能力处。

    ## ⚠️ `source_id` 是本测判别力的前提（实施期实测）
    旧 `_EVIL_TABLES` **无 `source_id`** ⇒ 会被 **② 的门**软降级 ⇒ 摘掉 v0.9.6 门后本测**照绿**，
    但绿的理由是「② 拦的」而非「③ 拦的」⇒ **③ 在测里根本没被验到**。
    ⇒ 现在给它绑一条**本租户的** http 数据源（`source_id`），让 ② 满足、把判别力交给 ③。
    取材=revert：把 `check_url_allowed(url)` 从 `execute` 里摘掉 → 出网探针炸 ⇒ 本测红。
    """
    from knot.services import http_planner
    sid = _plant_evil_http_source(2, "tenants/2")     # 库里已有一条坏行（绕过 API 写侧门）
    _set_allowlist(2, "")                             # 本租户 allowlist 显式为空 ⇒ 全拒绝
    _write_evil(2, "tenants/2", tables=_evil_tables(sid))
    tok = _in_real(2)                                 # ⇐ 必须真实行，否则读不到该列
    try:
        catalog.reload(strict=False)
        assert catalog.is_http_table("evil.exfil"), "前提：恶意表确实进了槽（否则本测在验一个不存在的问题）"
        route = http_planner.pick_http_route("看下持仓", intent="detail")
        assert route is not None, (
            "恶意表**未被路由** —— 那么本测就没验到 ③（拦它的是别的门）。\n"
            "v0.9.7 起路由命中是**预期**：② 已满足（spec 绑了本租户数据源）⇒ 拒绝该发生在执行处。")
        r = asyncio.run(http_planner.run_http_step("q", "evil.exfil", route[1]))
    finally:
        reset_active_tenant(tok)

    assert r["success"] is False, f"③ 失效：恶意主机的调用成功了：{r}"
    assert "不在本租户的出网白名单内" in r["error"], (
        f"不是 **③ 的 allowlist** 拦下的（可能是 ② 或别的关卡）：{r['error']!r}\n"
        "⇒ 断言用 allowlist 的**专属消息**而非 `error_kind` —— 两道门都抛 `HTTPAuthError`，"
        "`error_kind == 'http_auth'` 这个 oracle 分不清它们（v0.9.6 同款教训）。")
    assert no_network == [], f"③ 失效：真发出了请求 {no_network}"


@pytest.mark.parametrize("case", ["unbound", "not_allowlisted"])
def test_direct_run_http_step_is_refused_by_both_gates(case, two_tenants, no_network):
    """⭐⭐⭐ **绕过 `pick_http_route`、直呼 `run_http_step`** → 仍被拒 + **零出网**（两道门各一格）。

    这是本文件判别力最高的一条：它复现的正是**决策处挡不住的那条路** ——
    `run_http_step(refined_question, table_full_name, http_spec)` 是**公开函数、自带 spec、
    内部不重新求 route**；`api/query.py` 里 `pick_http_route`（`:292`）与 `run_http_step`（`:332`）
    是**两次独立调用**、中间只隔一个 `if` ⇒ monitor / 定时报表 / 混合路由 / re-run 任一条接进来，
    只要拿到一个 spec 就能绕过决策处。**故两道门都必须在能力处独立成立。**

    - `unbound`：spec **无 `source_id`** ⇒ **②** 拒（凭据未绑本租户数据源）
    - `not_allowlisted`：spec 绑了本租户数据源，但其 host 不在本租户 allowlist ⇒ **③** 拒

    ⚠️ 每格断言**该门的专属消息**（不是 `error_kind`）—— 两道门都抛 `HTTPAuthError`
    ⇒ `error_kind` 分不清是哪道拦的，摘掉一道另一道会替它「顶班」而测仍绿（v0.9.6 实证的同款陷阱）。
    取材=revert：摘 base_url 硬边界 → `unbound` 格红；摘 `check_url_allowed` → `not_allowlisted` 格红。
    """
    from knot.services import http_planner
    if case == "unbound":
        spec, expect = _UNBOUND_TABLES[0]["http_spec"], "未绑定本租户的数据源"
    else:
        sid = _plant_evil_http_source(2, "tenants/2")
        _set_allowlist(2, "")
        spec, expect = _evil_tables(sid)[0]["http_spec"], "不在本租户的出网白名单内"

    tok = _in_real(2)                                 # ⇐ 必须真实行（allowlist 列在里面）
    try:
        r = asyncio.run(http_planner.run_http_step("q", "evil.exfil", spec))
    finally:
        reset_active_tenant(tok)

    assert r["success"] is False, f"[{case}] 直呼 run_http_step 竟然成功了：{r}"
    assert expect in r["error"], (
        f"[{case}] 不是预期那道门拦的：{r['error']!r}（期望消息含 {expect!r}）")
    assert no_network == [], f"[{case}] 门失效：真发出了请求 {no_network}"


def test_non_owner_with_its_own_allowlist_is_allowed(two_tenants, no_network):
    """⭐⭐ **正对照（must #2）**：非起源租户把 host 配进**自己的** allowlist ⇒ 请求**真的发出**。

    没有这一条，②③ 可以靠「拦住所有非起源租户」通过 —— 那不是隔离，是**把功能删掉**
    （而 v0.9.6 的门正是那样，它是代偿控制、本片已摘）。
    ⚠️ oracle = **出网探针记录非空**（不是返回值）：探针「先记录、再抛」，其 AssertionError 会被
    `run_http_step` 的 `except Exception` 吞成普通失败 ⇒ 「有没有真发请求」在返回值里表示不出来。
    取材=revert：把 `resolve_allowed_hosts` 的 column 分支改成恒返 `set()` → 本测红（不再出网）。
    """
    from knot.services import http_planner
    sid = _plant_evil_http_source(2, "tenants/2")
    _set_allowlist(2, _EVIL_HOST)                     # ⇐ 部署方给这个租户开了这台主机
    tok = _in_real(2)                                 # ⇐ 必须真实行，否则该列读不到
    try:
        asyncio.run(http_planner.run_http_step("q", "evil.exfil", _evil_tables(sid)[0]["http_spec"]))
    finally:
        reset_active_tenant(tok)
    assert no_network, (
        "非起源租户即便把 host 配进**自己的** allowlist 也没能发出请求 ——\n"
        "⇒ 门变成了「非起源租户一律拒」= 把功能删掉，而不是「按租户判断」。\n"
        "（v0.9.6 的 owner 门就是那个形态；它是代偿控制，v0.9.7 已摘。）"
    )
    assert any(_EVIL_HOST in (u or "") for u in no_network), (
        f"发出的请求不是打向配置的 host：{no_network}")


# ⛔ `test_soft_degradation_logs` 已于 v0.9.7 退役 —— 它测的是 v0.9.6 Layer 0 的日志，
#    而 Layer 0 本身已随门一并摘除。**v0.7.29b 的教训（软降级必须记日志，否则静默落 SQL）没有丢**，
#    它转瞄了本片**新的**软降级点（spec 无 `source_id` → 落 SQL），守护在
#    `tests/adapters/test_http_spec_requires_source_id.py::test_pick_http_route_soft_degrades_without_source_id`
#    与 `::test_soft_degradation_log_does_not_leak_spec_values`（后者还多守了「日志只报键名不报值」）。


def test_egress_refusal_message_leaks_nothing(two_tenants, no_network):
    """⭐ **v0.9.7 转瞄**：出网拒绝消息不含 env 名 / 部署方表名 / **别的租户配置的 host** —— #262 那条缝。

    ## 转瞄前后
    v0.9.6 守的是 **owner 门**的消息；门已随 ②③ 落地摘除 ⇒ 现在**真实存在**的客户端可见消息是
    **③ 的 allowlist 拒绝**（`url_allowlist.check_url_allowed`）。同一条 #262 缝、新的落点。
    `run_http_step` 把 `str(e)` 放进 `result["error"]`，`api/query.py` **原样 yield 给客户端**
    ⇒ **这条消息就是用户看到的**。

    ## ⚠️ 判据是**内容级**，且刻意不照搬旧断言
    - 旧版断「消息不含数字」（防 tid 泄漏）—— **不能照搬**：新消息含**调用方自己给的 host**，
      而 host 合法含数字（`api2.example.com`）⇒ 会误伤。
    - 改断「**另一个租户配置的 host** 不出现」：这才是本片新引入的泄漏面
      （若消息枚举 allowlist，租户 A 就能读出租户 B / 部署方的主机清单）。
    取材=revert：把消息改回含 `(allowed: {sorted(...)})` → 本测红（那份清单里就有别人的 host）。
    """
    from knot.services import http_planner
    other_tenant_host = "tenant1-private-api.corp.local"
    _set_allowlist(1, other_tenant_host)              # 起源租户配了一台**自己的**主机
    sid = _plant_evil_http_source(2, "tenants/2")
    _set_allowlist(2, "")                             # 租户#2 显式全拒绝
    tok = _in_real(2)
    try:
        msg = asyncio.run(
            http_planner.run_http_step("q", "evil.exfil", _evil_tables(sid)[0]["http_spec"]))["error"]
    finally:
        reset_active_tenant(tok)

    assert other_tenant_host not in msg, (
        f"拒绝消息泄漏了**别的租户**配置的 host（{other_tenant_host!r}）：{msg!r}\n"
        "⇒ 消息在枚举 allowlist。per-tenant 化后这等于把跨租户/部署方的主机清单吐给调用方。")
    for bad in ("KNOT_", "JWT_SECRET", "MASTER_KEY", "_local_catalog", "OWNER_TENANT_ID"):
        assert bad not in msg, f"拒绝消息泄漏 {bad!r}：{msg!r}"

    # ⭐ should-fix（守护者 Stage 4 §III）：**来源标签不得进客户端消息**。
    # 标签本身不是 env 值（故躲过 #262 的 AST 哨兵），但 `env-fallback` 会告诉租户
    # 「部署方还没迁移到 per-tenant 列」—— 那是部署方的内部状态，不是租户该知道的。
    # 原先这条只是 `resolve_allowed_hosts` docstring 里的**散文规则、零守护** ——
    # 正是本弧反复证明挡不住漂移的形状（守护者原话）。
    labels = _observed_source_labels()
    assert labels >= {"column", "env-fallback", "unconfigured"}, (
        f"来源标签派生出 {sorted(labels)} —— 三态没有全被观察到 ⇒ 下面的守护会**空转**。\n"
        "（这条前提断言的存在本身就是判据：派生型 oracle 必须先证明它不是空的。）")
    for label in labels:
        assert label not in msg, (
            f"客户端可见消息含来源标签 {label!r}：{msg!r}\n"
            "⇒ 标签只该进日志。`env-fallback` 会把「部署方尚未迁移」这个内部状态告诉租户。")
    assert no_network == [], f"③ 失效：真发出了请求 {no_network}"


# ─── 结构哨兵（验收 7c / 8b / 8e）───────────────────────────────────────


def test_three_consumers_share_one_predicate():
    """⭐ 验收 7c：三个消费点**共用同一谓词**（一个谓词、多个执行点 ≠「N 份清单」）。

    多份**判断**才是 N 份清单病；多个**执行点**共用一个判断是正确形状。
    取材=injection：在任一消费点改成本地重写判定（如 `current_tenant()["id"] == 1`）→ 本测红。
    """
    # v0.9.7：消费者集随门的移除而变（实测 grep 全仓 = 恰这两处）。
    # `pick_http_route` 的 Layer 0 与 `execute` 的 owner 门都是 ②③ 未落地期间的**代偿控制**，已摘。
    consumers = {
        "knot/services/agents/catalog_loaders.py": "load_file_layer",       # ① file 层归起源租户
        "knot/adapters/http/url_allowlist.py": "resolve_allowed_hosts",     # ③ 起源租户回退 env
    }
    for rel, fn_name in consumers.items():
        tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == fn_name), None)
        assert fn is not None, f"{rel} 里找不到 {fn_name}"
        names = {a.name for n in ast.walk(fn) if isinstance(n, ast.ImportFrom) for a in n.names}
        names |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        assert "is_owner_tenant" in names, (
            f"{rel}::{fn_name} 未使用共用谓词 `is_owner_tenant` —— 三处判据会漂移")


def test_all_outbound_requests_calls_live_inside_execute():
    """⭐ 验收 8b：`adapters/http/**` 内**所有** `requests.*` 出网调用都在 `execute` 内。

    门在**能力**里 ⇒ 哨兵的职责变成守「**这个能力没有兄弟**」：若有人在 `execute` 外再加一个
    `requests.get`，门就被绕过（那才是新的能力点）。
    取材=injection：在 `executor.py` 的 `execute` **外**加一个 `requests.get(...)` → 本测红。
    """
    offenders = []
    for py in sorted((_REPO / "knot" / "adapters" / "http").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        inside = set()
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and fn.name == "execute":
                inside = {id(n) for n in ast.walk(fn)}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "requests"
                    and n.func.attr in ("get", "post", "put", "delete", "patch", "request", "head")):
                if id(n) not in inside:
                    offenders.append(f"{py.relative_to(_REPO)}:{n.lineno} requests.{n.func.attr}")
    assert not offenders, (
        "`adapters/http/**` 出现 `execute` **之外**的出网调用：\n  " + "\n  ".join(offenders)
        + "\n\n门装在 `execute` 内（能力行使处）⇒ 新的出网点就是新的能力点、绕过门。"
    )


def test_no_second_http_client_in_http_adapter():
    """⭐ 验收 8e：`adapters/http/**` **不得引入第二个 HTTP 客户端**。

    只看 `requests.*` 的 oracle **表示不了「换个库」这个事件** —— 有人改用 `httpx` 就绕过了上一条。
    ⚠️ **放行 `urllib.parse`**：`url_allowlist.py` 用它做 URL **解析**，**解析器不是客户端**
    （不放行会误报 —— 实读确认过）。
    取材=injection：加 `import httpx` → 本测红；`urllib.parse` 不得误报。
    """
    banned = {"httpx", "aiohttp", "http.client", "socket", "urllib.request", "urllib3", "pycurl"}
    offenders = []
    for py in sorted((_REPO / "knot" / "adapters" / "http").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods = [n.module]
            for m in mods:
                root = m.split(".")[0]
                if m in banned or (root in banned and root != "urllib"):
                    offenders.append(f"{py.relative_to(_REPO)}:{n.lineno} {m}")
    assert not offenders, (
        "`adapters/http/**` 引入了第二个 HTTP 客户端：\n  " + "\n  ".join(offenders)
        + "\n\n门与出网哨兵都建立在「唯一客户端 = `requests`，唯一出网点 = `execute`」之上。"
    )


# ─── 耦合 tripwire（验收 8c · 行为级）──────────────────────────────────


def test_rtgate_still_locks_second_tenant(two_tenants):
    """⭐⭐ **R-T-GATE 仍硬锁第二 active 租户**（**行为级**断言，不是存在性）。

    ⚠️ **为什么必须行为级**：断言「`assert_no_second_active_tenant_served` 那一行还在」只能抓**删除**，
    抓不住这四种「**事实上 lift 了而行还在**」：`if False:` 包起来 · 本体改 no-op ·
    **把调用点移到 tid 解析之后**（不再是第一行 ⇒ 对平台/无 token 路径失效）· 前面插 early return。
    ⇒ 这里断言的是**后果**：两个 active 租户时请求**仍 fail-closed**。
    **你要排除的事件是「R-T-GATE 事实上不再生效」，不是「那一行不见了」。**

    ## ⚠️ v0.9.7：本测**不是**因为摘门而失效 —— 它的**理由**换了，断言没换
    v0.9.6 时它的标题是「门存在 ⇒ R-T-GATE 未 lift」，理由是「门是代偿控制，lift 必须撞一条点名它的红测」。
    ②③ 落地、门已摘 ⇒ 那个理由过期了。但**断言本身仍然必要**：R-T-GATE 距离可以 lift 还差
    一串 blocker（见下方消息）⇒ 谁去 lift 都该撞上一条**告诉他还差什么**的红测。
    ⚠️ 实测坐实它「摘门后**不会红、会静默变绿而理由变假**」—— 因为它的断言是**纯行为级**、
    代码里根本不引用那道门（门只活在 `pytest.fail` 的消息和 docstring 里）。
    ⇒ **这类测最危险的失效形态不是转红，是「继续绿着，但守的已经不是原来那件事」。**
    取材=injection：注释掉 `resolve_for_request` 里那行 gate（或下述四种中和手法任一）→ 本测红。
    """
    from knot.api import tenant_resolution as tr
    from knot.core.tenant_context import TenantContextError

    class _Req:
        headers: dict = {}
        url = type("U", (), {"path": "/api/conversations"})()

    # ⚠️⚠️ **必须 `try/except/else`，不能用 `pytest.raises(..., match=...)`**（守护者 Stage 4 §II）：
    # `match=` 本身已保证「异常消息含 R-T-GATE」⇒ 紧随其后的 `assert ... , "<说明>"` **永不失败**
    # ⇒ 那段精心写的说明**永远不会被显示**；而**真实的**失败模式（有人 lift ⇒ 不抛）只会得到
    # pytest 的 `DID NOT RAISE TenantContextError`，**不点名任何门** ⇒ 「lift 就撞一条点名这个门的红测」
    # 这个设计意图在最后一寸失效。
    # ⭐ **这是同一个错的第四次**：门放「决定处」而非「能力处」（三次）→ 说明放「**成功路径**」
    # 而非「**失败路径**」（本次）。**统一判据：门装在能力被行使的那一行；消息挂在事情真的出错的那一行。**
    try:
        tr.resolve_for_request(_Req())
    except TenantContextError as e:
        assert "R-T-GATE" in str(e), f"fail-closed 了但不是 R-T-GATE 挡的：{e}"
    else:
        pytest.fail(
            "两个 active 租户时请求**未** fail-closed —— **R-T-GATE 事实上已不生效**。\n"
            "\n✅ B-3 三项已于 v0.9.6/v0.9.7 全部关闭（① file catalog owner-gate ·\n"
            "   ② per-tenant `http_spec` 凭据 · ③ egress 租户域化）—— 那部分不再是 blocker。\n"
            "⛔ **但 lift 仍差下列各项**（CLAUDE.md 的 R-T-GATE 就绪清单为准）：\n"
            "   · provisioning：`db_dir` UNIQUE + 格式约束 + **禁停用/删除起源租户**\n"
            "   · 登录 `company` 改必填（现未带则回退唯一 active 租户 = lift 后 fail-open）\n"
            "   · per-tenant 初始口令 / 一次性邀请流（现单一 `KNOT_INITIAL_ADMIN_PASSWORD`）\n"
            "   · **平台侧审计落点 `platform_audit`**（R-10 audit-on-drift 卡在这里）\n"
            "   · `/api/bi/scheduler/tick` 租户域化 · `_get_secret` 单一全局 + 公开默认值\n"
            "   · 启动/请求期残留的 `resolve_single_tenant`（生产 5 处）· `replicas=1` 运维门\n"
            "   · `_business_rules` 归正\n"
            "⇒ 若你正在 lift：把上列逐条清完，并在**同一个 PATCH** 里删掉本测（连同它的理由）。"
        )


# ─── 已知现状登记（验收 12 · xfail 非 strict）──────────────────────────


@pytest.mark.xfail(strict=False, reason="v0.9.6 已知现状：写入先提交、strict 校验后跑 —— 修它要动 admin 端点 + 想清既有数据，登记 backlog")
def test_catalog_put_should_not_persist_when_strict_validation_fails(two_tenants):
    """⚠️ **期望**行为：`PUT /api/admin/catalog` 的 strict 校验失败时**不应**留下已持久化的污染。

    实读现状（`api/catalog.py:119-122`）：`catalog_repo.update_catalog(1, **updates)` **先提交**、
    `catalog_loader.reload(strict=True)` **后跑** ⇒ 即使 strict 抛（调用方看到 5xx），
    **污染已持久化**，而查询路径用 `reload()`（strict=False）会把它**激活**。

    ⚠️ **本测刻意断言「期望行为」并标 `xfail(strict=False)`**，**不是**写成「通过测断言污染确实持久化」——
    后者会**惩罚将来修它的人**（修好即转红、只能删），与本片 R-v096-7 禁的形状同型
    （评审期我在同一张验收表相邻两行犯过同一个符号错）。
    `strict=False` ⇒ 修好时自然 XPASS 而不拦路。
    """
    from knot.repositories import catalog_repo
    tok = _in(2, "tenants/2")
    try:
        catalog_repo.update_catalog(1, tables=json.dumps(_UNBOUND_TABLES, ensure_ascii=False))
        # 期望：strict 校验失败 ⇒ 不留污染。现状：留了 ⇒ 本断言失败 ⇒ xfail。
        catalog_state.invalidate_all()
        catalog.reload(strict=False)
        assert not catalog.is_http_table("evil.exfil"), "strict 校验失败后污染仍被持久化并激活"
    finally:
        reset_active_tenant(tok)


# ─── 端点级（验收 9/10/11 · Stage 1' 必改清单第 5 项）─────────────────────


@pytest.fixture
def non_owner_client(tmp_path, monkeypatch):
    """**非 owner 租户是唯一 active** 的 TestClient + 其 admin 的 Bearer header。

    ⚠️ **为什么要「唯一 active」而不是「两个 active」**：R-T-GATE 的
    `assert_no_second_active_tenant_served()` 是 `resolve_for_request` 的**第一行**
    ⇒ 两个 active 时**整站 fail-closed**、端点根本走不到 ⇒ 端点级验收无法进行。
    ⇒ 造「tenant#1 suspended + tenant#2 active」这个**lift 后的近似形态**（唯一可服务者是非 owner）。
    """
    # ⚠️ 必须用 `NoAmbientTenantTestClient`（v0.9.4 R17 哨兵强制，实施期它抓了我一次）：
    # 裸 `TestClient` 会让 conftest autouse 的**环境 tenant ctx（tid=1 = owner）渗进请求**
    # ⇒ 本测可能**因为错误的原因而绿**（看的是 owner 的槽，不是中间件解析出的 tid=2）。
    # 那个哨兵守的正是「v0.9.4 发现的测试盲区」—— 它在这里保护的是**我这条测的判别力**。
    from knot.repositories import base, tenant_repo, user_repo
    from tests.conftest import NoAmbientTenantTestClient
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    conn = tenant_repo.get_platform_conn()
    conn.executescript(
        "INSERT INTO tenants (id,slug,name,status,db_dir) VALUES (1,'default','起源','suspended','tenants/1');"
        "INSERT INTO tenants (id,slug,name,status,db_dir) VALUES (2,'t2','T2','active','.');"
    )
    conn.commit()
    conn.close()
    tok = _in(2, ".")
    try:
        base.init_db()
        admin = user_repo.get_user_by_username("admin")
        if admin and admin.get("must_change_password"):
            user_repo.update_user(admin["id"], must_change_password=0)
        # ⭐ v0.9.19 D3 起**必须显式设**：`KNOT_INITIAL_ADMIN_PASSWORD` 只对**起源租户**生效，
        # 非起源租户 seed 的是**随机口令** ⇒ 本 fixture 此前能用 `admin123` 登录 tenant#2，
        # 靠的正是 D3 修掉的那个缺陷（「A 公司的口令能进 B 公司」）。
        # ⇒ 登录用的口令由**本测自己设定**，不再借一个跨租户共享的 seed 值。
        import bcrypt as _bcrypt
        user_repo.update_user(
            admin["id"], password_hash=_bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode())
        # ⚠️ 必须有**至少一个** datasource：`_infer_source_types_from_datasources` 对**空表**
        # ε2 fail-fast（`MetadataError: DataSource 表为空`）⇒ `PUT`/`reset` 走 `reload(strict=True)` 会 500，
        # 与本片的门无关。真实租户必有数据源 ⇒ 补一个 doris（**非 http**，故不影响 source_type 推断：
        # 无 http 型 datasource 时该函数原样返回 tables，而我们的恶意表本就带**显式** source_type）。
        from knot.repositories import data_source_repo
        data_source_repo.create_datasource(
            admin["id"], "t2-doris", "", "127.0.0.1", 9030, "u", "p", "db", db_type="doris")
    finally:
        reset_active_tenant(tok)
    catalog_state.invalidate_all()

    from knot.main import app
    with NoAmbientTenantTestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, f"非 owner 租户 admin 登录失败：{r.text}"
        yield c, {"Authorization": f"Bearer {r.json()['token']}"}


def test_endpoint_non_owner_catalog_has_no_file_layer(non_owner_client):
    """⭐ 验收 9：非 owner 租户 admin 的 `GET /api/admin/catalog` —— **file 层内容全缺席**。

    这一层承重：v0.9.5 抓到的 `defaults` 泄漏就住在**端点层** ——
    槽层守护绿而端点仍吐部署方内容是可能的（那次就是）。
    断言用「**file 层实际内容的缺席**」而非计数：从 `_load_from_files()` 现算出部署方的表名/关键词，
    断言它们**一个都不在**响应里（环境相关的量不写成数字 —— v0.9.3 §III-1 教训）。
    """
    client, headers = non_owner_client
    f_lex, f_tables, f_rules, _f_rel, _src = catalog_loaders._load_from_files()
    r = client.get("/api/admin/catalog", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    got_tables = {f"{t.get('db')}.{t.get('table')}" for t in body["current"]["tables"]}
    leaked = sorted({f"{t.get('db')}.{t.get('table')}" for t in (f_tables or [])} & got_tables)
    assert not leaked, f"部署方 file 层的表泄漏给非 owner 租户：{leaked}"
    leaked_kw = sorted(set(f_lex or {}) & set(body["current"]["lexicon"] or {}))
    assert not leaked_kw, f"部署方 file 层的 lexicon 关键词泄漏：{leaked_kw}"
    if (f_rules or "").strip():
        assert (f_rules or "").strip() not in (body["current"]["business_rules"] or ""), (
            "部署方**业务口径**泄漏给非 owner 租户 —— 这正是「禁半空」要防的那一项")


def test_endpoint_non_owner_reset_does_not_restore_deployment_defaults(non_owner_client):
    """⭐ 验收 10：非 owner 租户 `POST /api/admin/catalog/reset` **不恢复**部署方默认。

    `/reset` 的语义是「清 DB 覆盖、回退到默认」—— 而「默认」对非 owner 必须是**空**，不是部署方的 file 层。
    取材=revert：摘掉 `load_file_layer` 的判据 → reset 后部署方表回来 → 本测红。
    """
    client, headers = non_owner_client
    f_lex, f_tables, _r, _rel, _s = catalog_loaders._load_from_files()
    r = client.post("/api/admin/catalog/reset", json={}, headers=headers)
    assert r.status_code == 200, r.text
    body = client.get("/api/admin/catalog", headers=headers).json()
    got = {f"{t.get('db')}.{t.get('table')}" for t in body["current"]["tables"]}
    assert not ({f"{t.get('db')}.{t.get('table')}" for t in (f_tables or [])} & got), (
        f"reset 把部署方 file 层「恢复」给了非 owner 租户：{sorted(got)}")
    assert not (set(f_lex or {}) & set(body["current"]["lexicon"] or {}))


def test_endpoint_non_owner_malicious_put_writes_but_execution_is_refused(non_owner_client, no_network):
    """⭐ 端点级：非起源租户恶意 `PUT`（含 `source_type=http`）**写入成功**，但**执行被 ③ 拒** + 零出网。

    ⚠️ **本测刻意承认现状**：`PUT` 对 `tables` **只校验 `isinstance(v, list)`**
    （`source_type` / `http_spec` 零校验）⇒ 写入**会**成功。本片**不改那个校验**（已登记 backlog：
    动它要连带想清「既有已写入数据怎么办」）。
    ⇒ 答案是**在执行处拦**：写进去也用不了。若将来有人加了 PUT 侧校验，前半断言会红并提醒他同步本测。

    ## v0.9.7 语义反转
    v0.9.6 拦它的是 **owner 门**（「非 owner 一律不许用 HTTP」）；门已摘。
    现在拦它的是 **③ 的 per-tenant allowlist**：该租户的 `allowed_http_hosts` 里没有这台主机。
    ⚠️ 且给 spec 绑了**本租户的**数据源（`source_id`）—— 否则会被 **② 的门**拦住，
    于是「③ 拦住了它」这件事**在测里根本没被验到**（实施期实测的同款陷阱）。
    """
    from knot.services import http_planner
    client, headers = non_owner_client
    sid = _plant_evil_http_source(2, ".")             # 本租户的坏数据源行（绕过 API 写侧门）
    _set_allowlist(2, "")                             # 本租户 allowlist 显式全拒绝
    evil = _evil_tables(sid)
    r = client.put("/api/admin/catalog",
                   json={"tables": evil, "lexicon": _EVIL_LEXICON}, headers=headers)
    assert r.status_code == 200, f"现状是 PUT 零校验 ⇒ 应写入成功；若这里变了请同步本测：{r.text}"
    body = client.get("/api/admin/catalog", headers=headers).json()
    assert any(t.get("table") == "exfil" for t in body["current"]["tables"]), "前提：恶意表确实写进去了"

    tok = _in_real(2)
    try:
        res = asyncio.run(http_planner.run_http_step("q", "evil.exfil", evil[0]["http_spec"]))
    finally:
        reset_active_tenant(tok)
    assert "不在本租户的出网白名单内" in res["error"], (
        f"不是 ③ 的 allowlist 拦下的：{res['error']!r}（若是 ② 的消息，说明 source_id 没绑上，本测没验到 ③）")
    assert no_network == [], f"③ 失效：真发出了请求 {no_network}"


# ─── v0.9.16：私有 catalog 排出镜像 ⇒ 缺失时必须「退模板 + 响亮告警」 ───────────

def test_v0916_missing_private_catalog_falls_back_to_template(tmp_db_path, monkeypatch):
    """守什么：私有 catalog 缺失 ⇒ file 层退到**模板**（`source_tag == "example"`），不抛。

    取材：把 `_template_catalog.py` 也藏起来 ⇒ `source_tag` 变 `empty`（证明本测测的是那一级回退）。
    """
    import pathlib

    from knot.services.agents import catalog_loaders as cl

    real = pathlib.Path(cl.__file__).parent / "_local_catalog.py"
    if real.exists():
        monkeypatch.setattr(cl.importlib, "import_module",
                            lambda name: (_ for _ in ()).throw(ImportError(name)))
    tag = cl._load_from_files()[4]
    assert tag == "example", f"私有 catalog 缺失时未退到模板（source_tag={tag!r}）"


def test_v0916_missing_private_catalog_warns_loudly(tmp_db_path, monkeypatch):
    """⭐ 守什么：缺失时**响亮告警**（HTTP 会落 SQL）；文件在时**静默**。

    ⚠️ 这条是**排除动作的前提条件**：直接排而不告警 = 把泄漏换成静默正确性回归（R-v096-4 明禁）。
    取材：删掉 `warn_if_private_catalog_missing` 里的 `logger.warning` ⇒ 本测红。
    """
    import io
    import pathlib

    from knot.core.logging_setup import logger
    from knot.services.agents import catalog_loaders as cl

    monkeypatch.setattr(cl, "__file__", str(pathlib.Path(tmp_db_path).parent / "fake_loaders.py"))

    buf = io.StringIO()
    sid = logger.add(buf, format="{message}", level="WARNING")
    try:
        cl.warn_if_private_catalog_missing()
    finally:
        logger.remove(sid)
    out = buf.getvalue()
    assert "私有 catalog 未挂载" in out, f"缺失时没有告警 —— 静默落 SQL 复发：{out!r}"
    assert "静默落 SQL" in out, f"告警没说清后果，运维看不出要不要管：{out!r}"


# ─── v0.9.17：两条启动 WARN 与「租户数」解耦（lift 后仍须有效）───────────────

def _warn_output(fn) -> str:
    import io

    from knot.core.logging_setup import logger
    buf = io.StringIO()
    sid = logger.add(buf, format="{message}", level="WARNING")
    try:
        fn()
    finally:
        logger.remove(sid)
    return buf.getvalue()


def test_v0917_owner_inactive_warns_regardless_of_tenant_count(tmp_db_path):
    """守什么：起源租户被停用 ⇒ 告警；且**再多一个 active 租户也照样告警**。

    取材：把判据改回 `resolve_single_tenant()` ⇒ 两 active 时它 raise ⇒ WARN 静默 ⇒ 本测红。
    """
    from knot.repositories import tenant_repo
    from knot.services.agents import catalog_loaders as cl

    conn = tenant_repo.get_platform_conn()
    conn.execute("UPDATE tenants SET status='suspended' WHERE id=1")
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()

    out = _warn_output(cl.warn_if_owner_tenant_not_active)
    assert "起源租户" in out and "suspended" in out, f"起源租户被停用却没告警：{out!r}"


def test_v0917_private_catalog_warn_does_not_depend_on_tenant_count(tmp_db_path):
    """守什么：私有 catalog 缺失的告警**不依赖「恰 1 个 active 租户」**。

    取材：恢复 `resolve_single_tenant()` 前置 ⇒ 两 active 时早退 ⇒ 本测红。
    """
    import pathlib

    from knot.repositories import tenant_repo
    from knot.services.agents import catalog_loaders as cl

    conn = tenant_repo.get_platform_conn()
    conn.execute("INSERT INTO tenants (id,slug,name,status,db_dir) "
                 "VALUES (2,'t2','T2','active','tenants/2')")
    conn.commit()
    conn.close()

    if (pathlib.Path(cl.__file__).parent / "_local_catalog.py").exists():
        pytest.skip("本机存在真实私有 catalog；该分支由 v0.9.16 那条测覆盖")
    out = _warn_output(cl.warn_if_private_catalog_missing)
    assert "私有 catalog 未挂载" in out, f"两 active 租户下告警消失了：{out!r}"
