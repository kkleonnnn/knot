"""v0.9.3 — catalog 载体 per-tenant 化守护测。

覆盖守护者 Stage 4 预锁看点 1/2/3/5 + §6-1/2/3/4：
- §6-1 跨租户串供关闭（复刻测绘那个**已实证串供**的双租户形态 = 现成坏基线）
- §6-2 ⭐ 代理未被静默旁路（reload 后 6 名仍不在 `catalog.__dict__`）
- B-2 非对称：reload 只落**租户默认槽**，active catalog≠1 不产生第二个槽
- §6-4 单租户下 file HTTP 表仍被命中（防 `_parse_catalog_content` 造槽 → v0.7.29b 静默落 SQL 复发）
- F-1' 硬条件：lazy miss loader **两形态**冷槽 —— ① 有 catalog ctx（query 路径）② **无** catalog ctx
  （admin / 脱敏链等非 query 路径）。守护者明示「只测 query 路径不算普适」。

纯 in-process（`set_active_tenant`，永不 `resolve_single_tenant` → R-T-GATE 不动）。
注：一律 `reload(strict=False)` —— tmp 库无 data_sources 行，`strict=True` 会撞既有 ε2 fail-fast
（`_infer_source_types_from_datasources` 的「DataSource 表为空」熔断，与本片无关）；
strict=False 亦是 query 路径 `http_planner:130` 的真实用法。
"""
import json
import sqlite3

import pytest

from knot.core import tenant_context as tc
from knot.core.tenant_context import reset_active_tenant, set_active_tenant
from knot.services.agents import catalog, catalog_state

_CARRIER = ("LEXICON", "TABLES", "BUSINESS_RULES", "RELATIONS", "FIELD_LABELS", "_SOURCE")


@pytest.fixture
def two_tenants(tmp_path, monkeypatch):
    """tmp 数据根 + 两租户库，各自 catalogs id=1 灌**可区分**内容（复刻测绘坏基线形态）。"""
    from knot.repositories import base, catalog_repo, tenant_repo
    anchor = tmp_path / "knot.db"
    monkeypatch.setattr(base, "SQLITE_DB_PATH", str(anchor))
    monkeypatch.setattr(tenant_repo, "SQLITE_DB_PATH", str(anchor))
    tenant_repo.init_platform_db()
    tenant_repo.seed_default_tenant(db_dir="tenants/1")

    made = {}
    for tid, dbdir, tag in ((1, "tenants/1", "t1"), (2, "tenants/2", "t2")):
        tok = set_active_tenant({"id": tid, "db_dir": dbdir})
        try:
            base.init_db()
            catalog_repo.update_catalog(
                1,
                tables=json.dumps([{"db": f"{tag}_db", "table": f"secret_{tag}", "columns": []}]),
                lexicon=json.dumps({f"{tag}词": [f"{tag}_db.secret_{tag}"]}),
                business_rules=f"【租户{tid}机密业务规则】",
            )
            made[tid] = dbdir
        finally:
            reset_active_tenant(tok)
    catalog_state.invalidate_all()
    return made


def _in(tid, dbdir):
    return set_active_tenant({"id": tid, "db_dir": dbdir})


# ───────────────────────── §6-1 跨租户串供关闭 ─────────────────────────

def test_no_cross_tenant_bleed_across_all_six_carrier_names(two_tenants):
    """⭐ §6-1：租户#1 reload 后切租户#2（**不 reload**）→ 6 个载体名各自只见本租户内容。

    这是测绘阶段**已实证串供**的形态（当时 6 个 module global 全部双向串）。
    revert（载体回退成进程全局 / reload 用 `global` 赋值）→ 本测转红。
    """
    tok = _in(1, "tenants/1")
    try:
        assert catalog.reload(strict=False).startswith("db")
        assert "租户1" in catalog.BUSINESS_RULES
        assert catalog.get_table_full_names() == ["t1_db.secret_t1"]
    finally:
        reset_active_tenant(tok)

    tok = _in(2, "tenants/2")
    try:
        # 关键：**不 reload**，直接读 —— v0.9.3 前此处会拿到租户#1 的全部内容
        assert "租户2" in catalog.BUSINESS_RULES, "租户#2 读到别租户 business_rules（跨租户串供）"
        assert catalog.get_table_full_names() == ["t2_db.secret_t2"]
        assert "t2词" in catalog.LEXICON and "t1词" not in catalog.LEXICON
        assert catalog.current_catalog()["business_rules"].find("租户2") >= 0
    finally:
        reset_active_tenant(tok)

    # 反向：回租户#1 仍是自己的（不被租户#2 的 lazy load 覆盖）
    tok = _in(1, "tenants/1")
    try:
        assert "租户1" in catalog.BUSINESS_RULES
    finally:
        reset_active_tenant(tok)


# ───────────────────── §6-2 代理未被静默旁路（B-1）─────────────────────

def test_carrier_names_absent_from_module_namespace_after_reload(two_tenants):
    """⭐ §6-2 / Stage 4 看点 1：`reload()` **之后** 6 名仍不在 `catalog.__dict__`。

    B-1 实测：`global X; X = ...` 会把名字复活 → PEP 562 代理**静默死亡**、租户槽闲置、串供照旧且无异常；
    且 reload 在启动期与每 query 都跑 ⇒ 一旦复活即永久落静默支。
    revert（reload 改回 `global`+赋值）→ 本测转红。
    """
    tok = _in(1, "tenants/1")
    try:
        catalog.reload(strict=False)
        resurrected = [n for n in _CARRIER if n in vars(catalog)]
        assert not resurrected, f"载体名被复活进模块命名空间 → 代理静默失效：{resurrected}"
        catalog_state.assert_no_resurrected_globals()   # 生产同款断言
    finally:
        reset_active_tenant(tok)


def test_proxy_and_fallback_share_identity(two_tenants):
    """identity 契约（Codex R5）：代理与 `current_catalog()` fallback 读同一槽同一对象
    → `test_catalog_context.py:22-25` 三条 `is` 断言在 per-tenant 后仍成立。"""
    tok = _in(1, "tenants/1")
    try:
        catalog.reload(strict=False)
        cur = catalog.current_catalog()
        assert cur["tables"] is catalog.TABLES
        assert cur["lexicon"] is catalog.LEXICON
        assert cur["business_rules"] is catalog.BUSINESS_RULES
        assert cur["catalog_id"] is None
    finally:
        reset_active_tenant(tok)


# ─────────────── B-2 非对称：reload 只落租户默认槽 ───────────────

def test_reload_writes_only_default_slot_not_active_catalog(two_tenants):
    """⭐ Stage 4 看点 3 / R-2：即使 per-request active catalog ≠ 1，`reload()` 也只落**租户默认槽**。

    B-2 承重：`catalog_loaders._load_from_db` 硬编 `get_catalog(1)` ⇒ 若按 active catalog_id 分槽，
    active catalog=7 的用户每发一次 query 就把 catalog#1 的口径写进 (tid,7) 槽 = 租户内跨 catalog 污染。
    故载体**只有 tid 一维**：断言 reload 前后槽数不因 active catalog 变化而增加。
    """
    tok = _in(1, "tenants/1")
    try:
        catalog.reload(strict=False)
        n_before = len(catalog_state._state)
        # 模拟 query 路径：ctx 已是 active catalog=7，再触发一次 reload（pick_http_route 每 query 都会）
        ctok = catalog.set_active_catalog_ctx(
            {"lexicon": {}, "tables": [], "business_rules": "active-7",
             "relations": [], "field_labels": {}, "catalog_id": 7}
        )
        try:
            catalog.reload(strict=False)
            assert len(catalog_state._state) == n_before, "载体多出一槽 → 按 catalog_id 分槽了（破 R-2）"
            # ctx 仍优先（active catalog 语义不变）
            assert catalog.current_catalog()["business_rules"] == "active-7"
        finally:
            catalog._active_catalog_ctx.reset(ctok)
        # 默认槽内容仍是 DB catalog#1 的（未被 active-7 覆盖）
        assert "租户1" in catalog.BUSINESS_RULES
    finally:
        reset_active_tenant(tok)


# ───────── F-1' 硬条件：lazy miss loader **两形态**冷槽 ─────────

def test_cold_slot_lazy_loads_with_catalog_ctx(two_tenants):
    """F-1' 形态①（query 路径，**有** catalog ctx）：冷槽首访即完整加载。

    warm-up 与 import 期 reload 都已删 ⇒ 这是生产上冷槽的真实形态之一。
    """
    catalog_state.invalidate_all()
    tok = _in(1, "tenants/1")
    try:
        ctok = catalog.set_active_catalog_ctx(
            {"lexicon": {}, "tables": [], "business_rules": "from-ctx",
             "relations": [], "field_labels": {}, "catalog_id": 3}
        )
        try:
            assert catalog.current_catalog()["business_rules"] == "from-ctx"   # ctx 优先
            # 而绕 ctx 的 HTTP/表族仍须能工作（走租户槽 → 触发 lazy load）
            assert catalog.get_table_full_names() == ["t1_db.secret_t1"]
        finally:
            catalog._active_catalog_ctx.reset(ctok)
    finally:
        reset_active_tenant(tok)


def test_cold_slot_lazy_loads_without_catalog_ctx(two_tenants):
    """⭐ F-1' 形态②（**非 query** 路径，**无** catalog ctx）—— 守护者明示「只测 query 路径不算普适」。

    admin 屏 / 脱敏链 / conversations 这类路径从不 `capture_active_catalog`，删 warm-up 后它们是
    **第一个**碰到冷槽的消费者。断言：无 catalog ctx 时冷槽仍自动完整加载（不 raise、不返空）。
    """
    catalog_state.invalidate_all()
    assert catalog._active_catalog_ctx.get() is None, "本测前提：无 catalog ctx"
    tok = _in(2, "tenants/2")
    try:
        cur = catalog.current_catalog()          # 冷槽 + 无 ctx → lazy load 本租户默认 catalog
        assert "租户2" in cur["business_rules"]
        assert cur["catalog_id"] is None
        assert catalog.LEXICON.get("t2词") == ["t2_db.secret_t2"]
    finally:
        reset_active_tenant(tok)


def test_no_tenant_ctx_is_fail_closed(two_tenants):
    """D4'：无 **tenant** ctx → 读 catalog 一律 raise（不再静默回退进程全局供数）。"""
    catalog_state.invalidate_all()
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(tc.TenantContextError):
            _ = catalog.TABLES        # 代理读 → tenant_cache_key → current_tenant() raise
        with pytest.raises(tc.TenantContextError):
            catalog.current_catalog()
        with pytest.raises(tc.TenantContextError):
            catalog.get_http_tables()
    finally:
        tc._active_tenant_ctx.reset(tok)


# ───────── §6-4 file HTTP 表不因造槽方式而消失（v0.7.29b 防复发）─────────

def test_file_http_tables_survive_in_slot(two_tenants, monkeypatch):
    """⭐ Stage 4 看点 2：槽必须由**完整 reload 流水线**造（DB + file merge + 推断）。

    若改用 `_parse_catalog_content`（DB-only）造槽 → file HTTP 虚拟表消失 → `is_http_table()` 恒 False
    → `pick_http_route` 恒 None → **HTTP 查询静默落 SQL**（v0.7.29b bug 类复发）。
    这里注入一个 file 层 HTTP 表，断言它在槽里活着、且 `get_http_spec` 能取到。
    """
    http_tbl = {"db": "ext", "table": "live_api", "columns": [],
                "source_type": "http", "http_spec": {"url_template": "https://x/y", "method": "GET"}}
    # 注意 patch 的是 **catalog** 上的名字：catalog.py:22 用 from-import 绑了 `_load_from_files`，
    # patch 源模块 catalog_loaders 不影响已绑引用（本仓哨兵①禁的正是这类值绑，此处是函数版）。
    monkeypatch.setattr(
        catalog, "_load_from_files",
        lambda: ({"实时": ["ext.live_api"]}, [http_tbl], "file-rules", [], "real"),
    )
    catalog_state.invalidate_all()
    tok = _in(1, "tenants/1")
    try:
        catalog.reload(strict=False)
        assert catalog.is_http_table("ext.live_api"), "file HTTP 虚拟表从槽里消失 → pick_http_route 会恒 None"
        assert catalog.get_http_spec("ext.live_api")["url_template"] == "https://x/y"
        assert "ext.live_api" in catalog.get_http_tables()
        # DB 的 SQL 表仍在（file 只权威追加 HTTP 表，不覆盖 SQL 表）
        assert "t1_db.secret_t1" in catalog.get_table_full_names()
    finally:
        reset_active_tenant(tok)


def test_slot_producer_is_full_pipeline_not_db_only(two_tenants, monkeypatch):
    """⭐ Stage 4 看点 2 第二个接缝：DB `catalog#1` 的 business_rules **置空**而 file 非空时，
    ctx-free 读者仍须拿到 **file 规则**（`_parse_catalog_content` 造槽会给出 ""）。"""
    from knot.repositories import catalog_repo
    monkeypatch.setattr(
        catalog, "_load_from_files",
        lambda: ({}, [], "【file 层业务规则】", [], "real"),
    )
    catalog_state.invalidate_all()
    tok = _in(1, "tenants/1")
    try:
        catalog_repo.update_catalog(1, business_rules="")     # DB 侧置空 → 应 fallback 到 file
        catalog.reload(strict=False)
        assert catalog.BUSINESS_RULES == "【file 层业务规则】", (
            "槽丢了 file 层 fallback → 槽 producer 不是完整 reload 流水线（R-3'）"
        )
    finally:
        reset_active_tenant(tok)


def test_tenant_db_has_no_tenant_column(two_tenants):
    """R-1 / OOS-1v2：租户库 `catalogs` 表内**不得**出现 tenant_id/project_id 列（隔离靠文件边界）。"""
    tmp = two_tenants
    assert tmp  # fixture 已建两库
    from pathlib import Path

    from knot.repositories import base
    root = Path(base.SQLITE_DB_PATH).parent
    for dbdir in ("tenants/1", "tenants/2"):
        c = sqlite3.connect(root / dbdir / "knot.db")
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(catalogs)")}
        finally:
            c.close()
        assert not (cols & {"tenant_id", "project_id"}), f"{dbdir} catalogs 出现租户列（破 OOS-1v2）"


# ───────── D8' fail-closed 穷举（Codex R3；脱敏链安全最重）─────────

@pytest.mark.parametrize("call", [
    pytest.param(lambda: __import__("knot.services.desensitize", fromlist=["x"])
                 .non_admin_alias_map(), id="desensitize(脱敏链·安全最重)"),
    pytest.param(lambda: __import__("knot.services.llm_prompt_builder", fromlist=["x"])
                 .build_system_prompt("q", "## db.t", ""), id="llm_prompt_builder(RELATIONS 注入)"),
    pytest.param(lambda: __import__("knot.services.agents.sql_planner_prompts", fromlist=["x"])
                 ._relations_for_schema("## db.t"), id="sql_planner_prompts(关系段)"),
    pytest.param(lambda: __import__("knot.services.agents.catalog_loaders", fromlist=["x"])
                 ._load_from_db(), id="catalog_loaders(DB 源→legacy 兜底)"),
])
def test_no_tenant_ctx_never_degrades_silently(two_tenants, call):
    """⭐ D8' / Stage 4 看点 4：无 tenant ctx 时这些点必须 **raise 而非静默降级**。

    降级各自的后果：脱敏链返 {} → alias_map 空 → scrub 全 no-op → 非 admin 裸看内部库表名/错误原文（**安全**）；
    relations 段返 "" → LLM 无 JOIN 条件 → 隐式笛卡尔/错数；catalog_loaders 降级 → 把部署级 file/legacy
    catalog 当成该租户内容（全体租户共用一份）。
    revert（去掉 `isinstance(e, TenantContextError): raise` 守卫）→ 本测转红。
    """
    catalog_state.invalidate_all()
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(tc.TenantContextError):
            call()
    finally:
        tc._active_tenant_ctx.reset(tok)


def test_desensitize_alias_map_still_works_with_ctx(two_tenants):
    """反向（防上一条被"一律 raise"糊弄过去）：**有** tenant ctx 时脱敏 alias_map 正常构建、且是本租户词典。"""
    from knot.services.desensitize import non_admin_alias_map
    catalog_state.invalidate_all()
    tok = _in(2, "tenants/2")
    try:
        amap = non_admin_alias_map()
        assert amap, "有 ctx 时 alias_map 不该为空（否则脱敏 no-op）"
        assert any("t2" in k or "t2" in str(v) for k, v in amap.items()), amap
    finally:
        reset_active_tenant(tok)


def test_capture_active_catalog_fails_closed_without_tenant_ctx(two_tenants):
    """D8'：`capture_active_catalog` 的 fail-soft 不得吞缺-tenant-ctx（否则该请求被静默服务）。

    revert（去掉 query_helper 的 `isinstance(e, TenantContextError): raise`）→ 本测转红
    （原路径会 log warning 后返 None，请求继续跑）。
    """
    from knot.services import query_helper
    catalog_state.invalidate_all()
    tok = tc._active_tenant_ctx.set(None)
    try:
        with pytest.raises(tc.TenantContextError):
            query_helper.capture_active_catalog({"id": 1})
    finally:
        tc._active_tenant_ctx.reset(tok)


def test_observability_never_logs_catalog_content(two_tenants):
    """⭐ F-3'：观测只记规模/来源/耗时，**严禁记 catalog 内容**（business_rules/lexicon = 业务口径，敏感）。

    ⚠️ 必须挂 **loguru sink** 抓日志：本仓 logger 是 loguru（`core/logging_setup`），
    pytest 的 `caplog` 只抓 stdlib logging → 用 caplog 写这条测是 **tautology**
    （实测：把 business_rules 拼进日志后 caplog 版仍绿）。
    钉死方式：租户库的 business_rules 是「【租户1机密业务规则】」这种可检索标记串，断言其不出现在任何一行日志里。
    revert（把内容拼进 log）→ 本测转红（已实证）。
    """
    from loguru import logger as _lg
    sink: list = []
    hid = _lg.add(lambda m: sink.append(str(m)), level="DEBUG", format="{message}")
    catalog_state.invalidate_all()
    tok = _in(1, "tenants/1")
    try:
        catalog.reload(strict=False)          # 触发 publish 的 DEBUG 行
        catalog_state.invalidate_all()
        catalog.current_catalog()             # 触发冷槽加载的 INFO 行
    finally:
        reset_active_tenant(tok)
        _lg.remove(hid)
    blob = "".join(sink)
    assert "[catalog]" in blob, f"没抓到 catalog 观测日志（sink 失效则本测退化为 tautology）：{blob[:200]}"
    assert "机密业务规则" not in blob, f"日志泄漏 business_rules 内容：{blob[:300]}"
    assert "t1词" not in blob, f"日志泄漏 lexicon 内容：{blob[:300]}"
    assert "secret_t1" not in blob, f"日志泄漏表名内容：{blob[:300]}"
