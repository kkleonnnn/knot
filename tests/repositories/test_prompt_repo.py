"""prompt_repo happy-path 单测。"""
from bi_agent.repositories import prompt_repo


def test_default_empty(tmp_db_path):
    assert prompt_repo.get_prompt_template("clarifier") == ""
    assert prompt_repo.list_prompt_templates() == []


def test_set_and_get(tmp_db_path):
    prompt_repo.set_prompt_template("clarifier", "你是 X")
    assert prompt_repo.get_prompt_template("clarifier") == "你是 X"


def test_overwrite(tmp_db_path):
    prompt_repo.set_prompt_template("sql_planner", "v1")
    prompt_repo.set_prompt_template("sql_planner", "v2")
    assert prompt_repo.get_prompt_template("sql_planner") == "v2"


def test_delete(tmp_db_path):
    prompt_repo.set_prompt_template("presenter", "x")
    prompt_repo.delete_prompt_template("presenter")
    assert prompt_repo.get_prompt_template("presenter") == ""
