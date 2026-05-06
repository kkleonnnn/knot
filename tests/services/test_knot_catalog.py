"""services.knot.catalog happy-path 单测：DB → real → example fallback chain。"""
import os
import tempfile

import pytest


@pytest.fixture()
def tmp_db_path(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="bi_agent_test_")
    os.close(fd)
    os.unlink(path)
    from bi_agent.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_example_fallback_loaded_when_no_db_no_real(tmp_db_path):
    """无 DB 覆盖 + 无真实 ohx_catalog.py → 应加载 ohx_catalog.example.py。"""
    from bi_agent.services.knot import catalog
    catalog.reload()
    # source 至少是 example（如果开发机有 ohx_catalog.py 真实文件可能是 real）
    assert catalog._SOURCE in ("example", "real")
    assert isinstance(catalog.TABLES, list)
    assert isinstance(catalog.LEXICON, dict)


def test_db_override_takes_precedence(tmp_db_path):
    """DB 三键非空时优先于文件 fallback。"""
    from bi_agent.repositories.settings_repo import set_app_setting
    from bi_agent.services.knot import catalog

    set_app_setting("catalog.business_rules", "## DB-injected\nRule A")
    catalog.reload()
    assert catalog._SOURCE == "db"
    assert "DB-injected" in catalog.BUSINESS_RULES


def test_reset_db_falls_back_to_example(tmp_db_path):
    """清空 DB 三键 → 回退到文件 example/real。"""
    from bi_agent.repositories.settings_repo import set_app_setting
    from bi_agent.services.knot import catalog

    set_app_setting("catalog.business_rules", "X")
    catalog.reload()
    assert catalog._SOURCE == "db"

    set_app_setting("catalog.business_rules", "")
    catalog.reload()
    assert catalog._SOURCE in ("example", "real")


def test_get_defaults_from_files_returns_dict(tmp_db_path):
    from bi_agent.services.knot import catalog
    d = catalog.get_defaults_from_files()
    assert "tables" in d and "lexicon" in d and "business_rules" in d and "source" in d


def test_get_table_full_names(tmp_db_path):
    from bi_agent.services.knot import catalog
    catalog.reload()
    names = catalog.get_table_full_names()
    assert isinstance(names, list)
    if names:
        assert all("." in n for n in names)
