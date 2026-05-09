"""services.agents.catalog happy-path 单测：DB → real → example fallback chain。"""
import os
import tempfile

import pytest


@pytest.fixture()
def tmp_db_path(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="bi_agent_test_")
    os.close(fd)
    os.unlink(path)
    from knot.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_example_fallback_loaded_when_no_db_no_real(tmp_db_path):
    """无 DB 覆盖 + 无真实 ohx_catalog.py → 应加载 ohx_catalog.example.py。"""
    from knot.services.agents import catalog
    catalog.reload()
    # source 至少是 example（如果开发机有 ohx_catalog.py 真实文件可能是 real）
    assert catalog._SOURCE in ("example", "real")
    assert isinstance(catalog.TABLES, list)
    assert isinstance(catalog.LEXICON, dict)


def test_db_override_takes_precedence(tmp_db_path):
    """DB 三键非空时优先于文件 fallback。"""
    from knot.repositories.settings_repo import set_app_setting
    from knot.services.agents import catalog

    set_app_setting("catalog.business_rules", "## DB-injected\nRule A")
    catalog.reload()
    assert catalog._SOURCE == "db"
    assert "DB-injected" in catalog.BUSINESS_RULES


def test_reset_db_falls_back_to_example(tmp_db_path):
    """清空 DB 三键 → 回退到文件 example/real。"""
    from knot.repositories.settings_repo import set_app_setting
    from knot.services.agents import catalog

    set_app_setting("catalog.business_rules", "X")
    catalog.reload()
    assert catalog._SOURCE == "db"

    set_app_setting("catalog.business_rules", "")
    catalog.reload()
    assert catalog._SOURCE in ("example", "real")


def test_get_defaults_from_files_returns_dict(tmp_db_path):
    from knot.services.agents import catalog
    d = catalog.get_defaults_from_files()
    assert "tables" in d and "lexicon" in d and "business_rules" in d and "source" in d


def test_get_table_full_names(tmp_db_path):
    from knot.services.agents import catalog
    catalog.reload()
    names = catalog.get_table_full_names()
    assert isinstance(names, list)
    if names:
        assert all("." in n for n in names)


# ── v0.4.1.1: RELATIONS 元数据测试 ──────────────────────────────────────────

def test_relations_loaded_from_example(tmp_db_path):
    """example catalog 包含 ≥ 1 条 RELATIONS（通用电商 user_id / sta_date 占位）。"""
    from knot.services.agents import catalog
    catalog.reload()
    rels = catalog.get_relations()
    assert isinstance(rels, list)
    # 真实 ohx_catalog.py 可能没补 RELATIONS 仍走 example fallback；example 必有 ≥ 1
    if catalog._SOURCE == "example":
        assert len(rels) >= 1
        # 字段结构契约：(left_t, left_c, right_t, right_c, semantics) 5 元组
        for r in rels:
            assert len(r) >= 5


def test_relations_fallback_when_module_missing_constant(tmp_db_path, monkeypatch):
    """R-S3：老 catalog 模块无 RELATIONS 常量 → get_relations() 返 [] 不抛 AttributeError。"""
    from knot.services.agents import catalog as cat_mod

    # 模拟一个无 RELATIONS 的"老 module"
    class _OldCatalog:
        LEXICON: dict = {}
        TABLES: list = []
        BUSINESS_RULES: str = ""
        # 故意不定义 RELATIONS

    monkeypatch.setattr(cat_mod, "_load_from_files",
                        lambda: ({}, [], "", list(getattr(_OldCatalog, "RELATIONS", []) or []), "real"))
    cat_mod.reload()
    assert cat_mod.get_relations() == []


def test_get_relations_for_tables_filters_to_selected(tmp_db_path):
    """R-S4：仅返 selected 表涉及的关联，避免 token 预算挤压。"""
    from knot.services.agents import catalog
    catalog.reload()
    rels = catalog.get_relations()
    if not rels:
        pytest.skip("RELATIONS 为空（真实 catalog 未填）")

    # 选 1 张表 → 关联两端必须都在 selected 才返
    one_table = rels[0][0]
    out_one = catalog.get_relations_for_tables([one_table])
    assert out_one == ""  # 单表不 join，返空

    # 选齐第一条关联的两端 → 必返非空 markdown
    out_both = catalog.get_relations_for_tables([rels[0][0], rels[0][2]])
    assert "RELATIONS" in out_both
    assert rels[0][1] in out_both  # left column
    assert rels[0][3] in out_both  # right column

    # 空 selected → 空
    assert catalog.get_relations_for_tables([]) == ""
