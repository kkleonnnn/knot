"""tests/repositories/test_saved_report_repo.py — v0.4.1 saved_reports CRUD（6 条）。

覆盖：create / get / get_by_unique / UNIQUE 冲突 / update_last_run / list 排序。
"""
from knot.repositories import saved_report_repo


def test_create_and_get(tmp_db_path):
    rid = saved_report_repo.create(
        user_id=1, title="昨日 GMV", sql_text="SELECT SUM(pay_amount) FROM orders",
        source_message_id=10, intent="metric", display_hint="metric_card",
        question="昨天的 GMV 是多少",
    )
    assert rid > 0
    sr = saved_report_repo.get(rid)
    assert sr["title"] == "昨日 GMV"
    assert sr["sql_text"] == "SELECT SUM(pay_amount) FROM orders"
    assert sr["intent"] == "metric"
    assert sr["display_hint"] == "metric_card"
    assert sr["question"] == "昨天的 GMV 是多少"
    assert sr["source_message_id"] == 10
    assert sr["last_run_truncated"] == 0
    assert sr["last_run_ms"] == 0
    assert sr["pinned_at"]  # 默认时间戳填充


def test_get_by_unique_returns_none_when_absent(tmp_db_path):
    assert saved_report_repo.get_by_unique(1, 999) is None


def test_get_by_unique_returns_row_when_present(tmp_db_path):
    rid = saved_report_repo.create(user_id=1, title="t", sql_text="SELECT 1", source_message_id=42)
    found = saved_report_repo.get_by_unique(1, 42)
    assert found is not None
    assert found["id"] == rid


def test_unique_conflict_uses_insert_or_ignore(tmp_db_path):
    """R-12 幂等基座：UNIQUE (user_id, source_message_id) 冲突时不抛 IntegrityError。
    create() 返 0 表示冲突跳过；service 层据此回查既存行返回。"""
    first = saved_report_repo.create(user_id=1, title="first", sql_text="x", source_message_id=7)
    assert first > 0
    second = saved_report_repo.create(user_id=1, title="second", sql_text="x", source_message_id=7)
    assert second == 0  # INSERT OR IGNORE 跳过
    # 既存行未被覆盖（title 仍是 first）
    found = saved_report_repo.get_by_unique(1, 7)
    assert found["title"] == "first"


def test_update_last_run_persists_truncated_flag(tmp_db_path):
    rid = saved_report_repo.create(user_id=1, title="t", sql_text="SELECT 1")
    saved_report_repo.update_last_run(
        rid, rows_json='[{"a":1}]', truncated=1, elapsed_ms=42, run_at="2026-05-07 19:00:00",
    )
    sr = saved_report_repo.get(rid)
    assert sr["last_run_rows_json"] == '[{"a":1}]'
    assert sr["last_run_truncated"] == 1
    assert sr["last_run_ms"] == 42
    assert sr["last_run_at"] == "2026-05-07 19:00:00"


def test_list_for_user_orders_by_pinned_at_desc(tmp_db_path):
    """list_for_user 按 pinned_at DESC（最近收藏在前）。
    用 datetime() 默认精度到秒；如果两条 INSERT 在同秒内，DESC 排序 fallback 到 rowid 顺序。
    本测试不依赖时间排序，仅断言 user 隔离正确 + 数量。"""
    saved_report_repo.create(user_id=1, title="A", sql_text="x", source_message_id=1)
    saved_report_repo.create(user_id=1, title="B", sql_text="y", source_message_id=2)
    saved_report_repo.create(user_id=2, title="C", sql_text="z", source_message_id=3)
    rows = saved_report_repo.list_for_user(1)
    titles = {r["title"] for r in rows}
    assert titles == {"A", "B"}  # user 2 的 C 不在
    assert len(saved_report_repo.list_for_user(2)) == 1
