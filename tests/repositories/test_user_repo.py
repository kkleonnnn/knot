"""user_repo happy-path 单测。"""
from knot.repositories import user_repo


def test_seed_admin_exists(tmp_db_path):
    u = user_repo.get_user_by_username("admin")
    assert u is not None
    assert u["role"] == "admin"
    assert u["username"] == "admin"


def test_get_user_by_id(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    fetched = user_repo.get_user_by_id(admin["id"])
    assert fetched["id"] == admin["id"]


def test_get_user_by_id_missing(tmp_db_path):
    assert user_repo.get_user_by_id(99999) is None


def test_create_user_and_list(tmp_db_path):
    ok = user_repo.create_user(
        username="alice", password_hash="x", display_name="Alice", role="analyst",
        doris_host=None, doris_port=9030, doris_user=None, doris_password=None, doris_database=None,
    )
    assert ok is True
    users = user_repo.list_users()
    assert any(u["username"] == "alice" for u in users)


def test_create_user_duplicate_returns_false(tmp_db_path):
    user_repo.create_user("bob", "h", "Bob", "analyst", None, 9030, None, None, None)
    ok = user_repo.create_user("bob", "h", "Bob", "analyst", None, 9030, None, None, None)
    assert ok is False


def test_update_user(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user(admin["id"], display_name="超级管理员")
    fetched = user_repo.get_user_by_id(admin["id"])
    assert fetched["display_name"] == "超级管理员"


def test_update_user_usage_accumulates(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user_usage(admin["id"], input_tokens=100, output_tokens=50,
                                cost_usd=0.01, query_time_ms=200)
    user_repo.update_user_usage(admin["id"], input_tokens=200, output_tokens=100,
                                cost_usd=0.02, query_time_ms=300)
    usage = user_repo.get_user_monthly_usage(admin["id"])
    assert usage["query_count"] == 2
    assert usage["monthly_tokens"] == 100 + 50 + 200 + 100
    assert abs(usage["monthly_cost_usd"] - 0.03) < 1e-9


def test_get_monthly_cost_aggregates(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    user_repo.update_user_usage(admin["id"], 10, 5, 0.05, 100)
    total = user_repo.get_monthly_cost()
    assert total == 0.05


def test_user_agent_model_config_roundtrip(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    user_repo.set_user_agent_model_config(admin["id"], {"clarifier": "claude-haiku-4-5-20251001"})
    cfg = user_repo.get_user_agent_model_config(admin["id"])
    assert cfg == {"clarifier": "claude-haiku-4-5-20251001"}


def test_user_agent_model_config_empty_default(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    cfg = user_repo.get_user_agent_model_config(admin["id"])
    assert cfg == {}
