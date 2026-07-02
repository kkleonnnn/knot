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
_MUTABLE_GLOBALS = {"LEXICON", "TABLES", "BUSINESS_RULES", "RELATIONS", "_SOURCE"}


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
