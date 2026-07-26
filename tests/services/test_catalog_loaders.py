"""收官③ catalog 拆分 live-read 命门哨兵（v0.6.5.12 R-CS-1/2；守护者 Stage 3 §B 重写）。

主哨 = **静态 forbid**：全仓（knot/+tests/）**0 个** `from (...services.agents.catalog) import <5 mutable global>`
—— 直禁造成 facade-freeze 的值绑定模式（catalog.reload() reassign global 后，值绑定快照变陈旧 →
`X.LEXICON` 静默读空 → 脱敏失效 / 选表 0 分；**不会 CI 红**，故须静态禁绝 + 防未来回归）。纯 ast，本地可验。
副哨：catalog_loaders 0 import catalog（Contract 8 测试侧冗余）+ reload() **函数**（非 importlib）后 module-attr live 反映。
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CATALOG_MOD = "knot/services/agents/catalog.py"
# v0.9.3 R-9 哨兵三件套：补 FIELD_LABELS（v0.7.27 引入后一直在哨兵外 —— 双向变异实验坐实漏检）。
_MUTABLE_GLOBALS = {"LEXICON", "TABLES", "BUSINESS_RULES", "RELATIONS", "FIELD_LABELS", "_SOURCE"}


def _py_files():
    for base in ("knot", "tests"):
        yield from (_REPO / base).rglob("*.py")


def _is_stateful_catalog(node: ast.ImportFrom) -> bool:
    """node 是否 from 有状态 catalog 模块（非 catalog_loaders / catalog_repo）。"""
    if node.module == "knot.services.agents.catalog":
        return True
    # 相对 import：from .catalog import / from ..agents.catalog import（末段恰为 catalog）
    if node.level and node.module and node.module.split(".")[-1] == "catalog":
        return True
    return False


def test_no_value_binding_from_import_of_catalog_globals():
    """主哨（本地 ast）：全仓 0 个 `from ...catalog import <5 global>` —— 禁绝 facade-freeze 值绑定。"""
    offenders = []
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and _is_stateful_catalog(node):
                frozen = {a.name for a in node.names} & _MUTABLE_GLOBALS
                if frozen:
                    offenders.append(
                        f"{p.relative_to(_REPO)}:{node.lineno} "
                        f"from {node.module} import {sorted(frozen)}"
                    )
    assert not offenders, (
        "facade-freeze 值绑定模式（reload reassign 后快照陈旧 → 静默空 catalog；须 `import catalog` "
        "module-attr live 读）：\n  " + "\n  ".join(offenders)
    )


def test_catalog_py_has_no_global_statement_on_carrier_names():
    """⭐ v0.9.3 R-9 哨兵②（B-1 实测推出）：catalog.py 内**禁** `global <6 名>` 语句。

    实测过的失效机制（最小复刻模块）：PEP 562 模块 `__getattr__` 只在常规属性查找**失败**时触发；
    一旦模块内出现 `global TABLES; TABLES = ...`，那 6 名就被**复活**进模块 `__dict__` →
    代理**静默死亡**（不报错）、per-tenant 槽闲置、跨租户串供照旧。
    **时序真相**：`reload()` 在启动期与每 query 都跑 ⇒ 一旦跑过就永久落在静默支
    （NameError 那支只存在于首次 reload 之前，反而是幸运情况）。
    → 故此哨兵与「禁 from-import 值绑」同等承重：后者防外部值绑，本条防内部复活。
    """
    tree = ast.parse((_REPO / _CATALOG_MOD).read_text(encoding="utf-8"))
    offenders = [
        f"{_CATALOG_MOD}:{n.lineno} global {sorted(set(n.names) & _MUTABLE_GLOBALS)}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Global) and (set(n.names) & _MUTABLE_GLOBALS)
    ]
    assert not offenders, (
        "catalog.py 内 `global <载体名>` 会把该名复活进模块 __dict__ → PEP 562 代理静默失效、"
        "租户槽闲置、跨租户串供照旧（且无任何异常）。reload 须用局部变量构造 + 原子发布到载体：\n  "
        + "\n  ".join(offenders)
    )


def test_catalog_py_has_no_bare_name_read_of_carrier():
    """⭐ v0.9.3 R-9 哨兵③：catalog.py 函数体内**禁裸名读**那 6 名（`LOAD_GLOBAL` 永不触发 `__getattr__`）。

    B-1：模块内 `for t in TABLES` 这类读法在代理方案下要么 NameError（首次 reload 前），
    要么读到被复活的进程全局（reload 后）—— 两支都错。内部一律走显式载体访问器。
    """
    tree = ast.parse((_REPO / _CATALOG_MOD).read_text(encoding="utf-8"))
    offenders = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node.id in _MUTABLE_GLOBALS):
                offenders.append(f"{_CATALOG_MOD}:{node.lineno} in {fn.name}(): 裸名读 {node.id}")
    assert not offenders, (
        "catalog.py 内部裸名读载体名 → 编译成 LOAD_GLOBAL，永不触发 PEP 562 代理（B-1）。"
        "改走显式载体访问器：\n  " + "\n  ".join(offenders)
    )


def test_no_setattr_on_carrier_names_anywhere():
    """⭐ v0.9.3 R-9 哨兵④（守护者 F-5'(c)，**顺序无关**）：全仓禁 `setattr(<any>, "<载体名>", ...)`。

    实测机制（比"污染后续测试"更糟）：`monkeypatch.setattr(catalog, "LEXICON", x)` 时 monkeypatch 先
    `getattr` 存"原值" —— **PEP 562 代理会响应它** → monkeypatch 认定该属性本就在 `__dict__` →
    teardown 时把存下的值 **`setattr` 回 `__dict__`**（而非 `delattr`）→ 该名**永久驻留**且成为**冻结快照**
    ⇒ 代理静默死亡 + 恢复本仓原哨兵要防的 facade-freeze，只是改从 monkeypatch 进来。
    本哨兵与「顺序」无关（纯 AST，不依赖测执行序）—— 这点重要：v0.9.3 前的 3 处 poisoner 位于
    `tests/services/`（收集序早于 `tests/` 根），靠运行期断言只能在**它们之后**的测里发现。
    """
    offenders = []
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and len(node.args) >= 2):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name != "setattr":
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and arg.value in _MUTABLE_GLOBALS:
                offenders.append(f"{p.relative_to(_REPO)}:{node.lineno} setattr(..., {arg.value!r}, ...)")
    assert not offenders, (
        "setattr 载体名会把该名写进模块 __dict__ → PEP 562 代理永久失效（monkeypatch teardown 亦不会 "
        "delattr，反而把冻结快照 setattr 回去）。改用 catalog_state.publish(...) 显式发布整槽：\n  "
        + "\n  ".join(offenders)
    )


def test_catalog_loaders_does_not_import_catalog():
    """副哨（本地 ast）：catalog_loaders 不 import 有状态 catalog（Contract 8 测试侧冗余 + 纯-loader 单向）。"""
    src = (_REPO / "knot" / "services" / "agents" / "catalog_loaders.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            assert not _is_stateful_catalog(node), f"catalog_loaders L{node.lineno} 不得 import catalog（破单向）"
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name != "knot.services.agents.catalog", f"catalog_loaders L{node.lineno} 不得 import catalog"


def test_reload_function_repopulates_module_attr_live():
    """副哨（CI — 需 app deps）：catalog.reload() **函数**（非 importlib）后 current_catalog 全局回退 = module-attr 同对象。"""
    from knot.services.agents import catalog

    src = catalog.reload()  # 函数调用（非 importlib.reload）；global reassign 在 catalog.py 同模块生效
    assert isinstance(src, str)  # reload 返 source tag
    # live-read 契约：ContextVar 未 set → current_catalog 回退读 module globals（与直读 catalog.LEXICON 同对象）
    cc = catalog.current_catalog()
    assert cc["lexicon"] is catalog.LEXICON
    assert cc["tables"] is catalog.TABLES
    assert cc["relations"] is catalog.RELATIONS
    assert cc["field_labels"] is catalog.FIELD_LABELS   # v0.7.27 两载体对称（全局回退路径 R-SL-189）


def test_reload_fallback_field_labels_no_nameerror(monkeypatch):
    """🔴 守护者 Stage 3 承重（R-SL-189.1）：`_load_from_db` 抛错 → reload except fallback :107
    须 +6th `{}` → `FIELD_LABELS == {}` 不 NameError（5→6-tuple 若漏 :107 解包点，DB 失败路径
    `db_field_labels` 未赋值 → 下游 `FIELD_LABELS = db_field_labels` NameError；latent 仅 DB-fail 触发）。"""
    from knot.models.errors import MetadataError
    from knot.services.agents import catalog

    def _boom():
        raise MetadataError("simulated DB unavailable（模拟真空期熔断）")
    monkeypatch.setattr(catalog, "_load_from_db", _boom)
    src = catalog.reload(strict=False)   # strict=False 降级不 raise；关键：不 NameError
    assert isinstance(src, str)
    assert catalog.FIELD_LABELS == {}    # :107 fallback +6th {} 生效（承重）
    assert catalog.current_catalog()["field_labels"] == {}
    # 注：monkeypatch teardown 自动复原 _load_from_db；FIELD_LABELS 留 {} = 默认态无害（后续 reload 自愈）


def test_parse_catalog_content_field_labels_per_user_carrier():
    """v0.7.27 两载体对称（R-SL-189）：per-user `_parse_catalog_content` 解析 field_labels
    （dict / 坏 JSON / 非 dict / 缺失 → fail-open {}）—— 与全局 `_load_from_db` 载体对称。"""
    from knot.services import query_helper
    assert query_helper._parse_catalog_content(
        {"id": 1, "field_labels": '{"market":"交易对"}'})["field_labels"] == {"market": "交易对"}
    assert query_helper._parse_catalog_content(
        {"id": 1, "field_labels": "not json"})["field_labels"] == {}       # 坏 JSON → {}
    assert query_helper._parse_catalog_content(
        {"id": 1, "field_labels": '["a","b"]'})["field_labels"] == {}      # 非 dict → {}
    assert query_helper._parse_catalog_content({"id": 1})["field_labels"] == {}  # 缺失 → {}


def test_reload_file_http_overrides_db_shadow(monkeypatch):
    """v0.7.29 b merge 权威：file HTTP 表【覆盖】同名 DB 手灌影子（部署代码层 > admin DB；防 problem 1
    静默落 SQL）；non-collision file http 仍追加；正常 SQL 表保留。"""
    from knot.services.agents import catalog
    db_tables = [
        {"db": "shop", "table": "orders"},                    # 正常 SQL 表（无 http 同名）
        {"db": "futures_admin", "table": "pos"},              # 🔴 手灌影子（缺 source_type=http）
    ]
    file_tables = [
        {"db": "futures_admin", "table": "pos", "source_type": "http"},   # 权威 file http（同名 → 覆盖影子）
        {"db": "futures_admin", "table": "orders_rt", "source_type": "http"},  # non-collision → 追加
    ]
    monkeypatch.setattr(catalog, "_load_from_db", lambda: ({}, db_tables, "", [], {}, True))
    monkeypatch.setattr(catalog, "_load_from_files", lambda: ({}, file_tables, "", [], "file"))
    monkeypatch.setattr(catalog, "_infer_source_types_from_datasources", lambda t: t)  # 隔离推断熔断
    catalog.reload(strict=False)
    pos = [t for t in catalog.TABLES if (t["db"], t["table"]) == ("futures_admin", "pos")]
    assert len(pos) == 1 and pos[0].get("source_type") == "http", (
        "file http 权威覆盖影子：同名去重 + source_type=http 生效（防 pick_http_route 漏）"
    )
    assert any((t["db"], t["table"]) == ("shop", "orders") for t in catalog.TABLES), "正常 SQL 表保留"
    assert any((t["db"], t["table"]) == ("futures_admin", "orders_rt") for t in catalog.TABLES), (
        "non-collision file http 仍追加（旧行为保持）"
    )
    # 注：monkeypatch teardown 复原 loader；TABLES 留此态无害（后续 reload 自愈，同 fallback 测试）
