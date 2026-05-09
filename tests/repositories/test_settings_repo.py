"""settings_repo happy-path 单测。"""
from knot.repositories import settings_repo


def test_app_setting_get_default(tmp_db_path):
    assert settings_repo.get_app_setting("nonexistent", "fallback") == "fallback"


def test_app_setting_set_get(tmp_db_path):
    settings_repo.set_app_setting("foo", "bar")
    assert settings_repo.get_app_setting("foo") == "bar"


def test_app_setting_overwrite(tmp_db_path):
    settings_repo.set_app_setting("k", "v1")
    settings_repo.set_app_setting("k", "v2")
    assert settings_repo.get_app_setting("k") == "v2"


def test_app_setting_empty_string_semantics(tmp_db_path):
    """v0.2.5 catalog reset 依赖：空字符串 = 清空覆盖。"""
    settings_repo.set_app_setting("catalog.business_rules", "X")
    assert settings_repo.get_app_setting("catalog.business_rules") == "X"
    settings_repo.set_app_setting("catalog.business_rules", "")
    assert settings_repo.get_app_setting("catalog.business_rules") == ""


def test_agent_model_config_roundtrip(tmp_db_path):
    cfg = {"clarifier": "claude-haiku-4-5-20251001",
           "sql_planner": "anthropic/claude-sonnet-4"}
    settings_repo.set_agent_model_config(cfg)
    assert settings_repo.get_agent_model_config() == cfg


def test_agent_model_config_empty_default(tmp_db_path):
    assert settings_repo.get_agent_model_config() == {}


def test_model_settings_default_empty(tmp_db_path):
    assert settings_repo.get_model_settings() == []


def test_set_default_model_clears_others(tmp_db_path):
    settings_repo.set_default_model("model-a")
    settings_repo.set_default_model("model-b")
    rows = {r["model_key"]: dict(r) for r in settings_repo.get_model_settings()}
    assert rows["model-a"]["is_default"] == 0
    assert rows["model-b"]["is_default"] == 1


def test_set_model_enabled_toggle(tmp_db_path):
    settings_repo.set_model_enabled("xyz", 0)
    settings_repo.set_model_enabled("xyz", 1)
    rows = {r["model_key"]: dict(r) for r in settings_repo.get_model_settings()}
    assert rows["xyz"]["enabled"] == 1
