"""data_source_repo happy-path 单测。"""
from knot.repositories import data_source_repo, user_repo


def test_create_list_get(tmp_db_path):
    sid = data_source_repo.create_datasource(
        user_id=1, name="prod", description="主库",
        db_host="h", db_port=9030, db_user="u", db_password="p", db_database="d",
    )
    assert data_source_repo.get_datasource(sid)["name"] == "prod"
    assert len(data_source_repo.list_datasources()) == 1


def test_update_and_delete(tmp_db_path):
    sid = data_source_repo.create_datasource(1, "x", "", "h", 9030, "u", "p", "d")
    data_source_repo.update_datasource(sid, name="renamed")
    assert data_source_repo.get_datasource(sid)["name"] == "renamed"
    data_source_repo.delete_datasource(sid)
    assert data_source_repo.get_datasource(sid) is None


def test_user_sources_assignment(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    s1 = data_source_repo.create_datasource(1, "a", "", "h", 9030, "u", "p", "d")
    s2 = data_source_repo.create_datasource(1, "b", "", "h", 9030, "u", "p", "d")
    data_source_repo.set_user_sources(admin["id"], [s1, s2])
    ids = data_source_repo.get_user_source_ids(admin["id"])
    assert sorted(ids) == sorted([s1, s2])


def test_set_user_sources_replaces(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    s1 = data_source_repo.create_datasource(1, "a", "", "h", 9030, "u", "p", "d")
    data_source_repo.set_user_sources(admin["id"], [s1])
    data_source_repo.set_user_sources(admin["id"], [])
    assert data_source_repo.get_user_source_ids(admin["id"]) == []


def test_get_all_user_source_ids(tmp_db_path):
    admin = user_repo.get_user_by_username("admin")
    s = data_source_repo.create_datasource(1, "a", "", "h", 9030, "u", "p", "d")
    data_source_repo.set_user_sources(admin["id"], [s])
    all_map = data_source_repo.get_all_user_source_ids()
    assert all_map[admin["id"]] == [s]
