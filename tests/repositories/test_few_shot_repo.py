"""few_shot_repo happy-path 单测。"""
from bi_agent.repositories import few_shot_repo


def test_empty_initial(tmp_db_path):
    assert few_shot_repo.list_few_shots() == []


def test_create_and_list(tmp_db_path):
    fid = few_shot_repo.create_few_shot("昨天注册数", "SELECT COUNT(*) FROM ...", type_="metric")
    rows = few_shot_repo.list_few_shots()
    assert len(rows) == 1
    assert rows[0]["id"] == fid
    assert rows[0]["type"] == "metric"
    assert rows[0]["is_active"] == 1


def test_update_few_shot(tmp_db_path):
    fid = few_shot_repo.create_few_shot("Q", "SELECT 1")
    few_shot_repo.update_few_shot(fid, sql="SELECT 2", type="trend")
    rows = few_shot_repo.list_few_shots()
    assert rows[0]["sql"] == "SELECT 2"
    assert rows[0]["type"] == "trend"


def test_only_active_filter(tmp_db_path):
    a = few_shot_repo.create_few_shot("A", "S", is_active=1)
    b = few_shot_repo.create_few_shot("B", "S", is_active=0)
    active = few_shot_repo.list_few_shots(only_active=True)
    assert len(active) == 1
    assert active[0]["question"] == "A"


def test_delete_few_shot(tmp_db_path):
    fid = few_shot_repo.create_few_shot("Q", "S")
    few_shot_repo.delete_few_shot(fid)
    assert few_shot_repo.list_few_shots() == []


def test_bulk_insert_skips_empty_rows(tmp_db_path):
    n = few_shot_repo.bulk_insert_few_shots([
        {"question": "Q1", "sql": "S1"},
        {"question": "", "sql": "skip-no-q"},
        {"question": "Q2", "sql": "S2", "type": "rank"},
    ])
    # bulk_insert_few_shots 返回 len(items) 不是 inserted；只验证 DB 数据
    rows = few_shot_repo.list_few_shots()
    assert len(rows) == 2
    assert {r["question"] for r in rows} == {"Q1", "Q2"}
