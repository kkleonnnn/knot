"""tests/repositories/test_bi_report_repo.py — v0.8.5 (②a) BI report_folders + bi_reports CRUD。

覆盖：folder create/get/list/update(rename+move+reorder)/delete +
report create/get/list/update(含 folder_id NULL 移动)/update_last_run(refresh_seq bump)/delete。
R-BI-1：全新表，与 saved_reports 0 交集（本文件不 import saved_report_repo）。
"""
from knot.repositories import bi_report_repo as repo

# ─── report_folders ──────────────────────────────────────────────────────────

def test_folder_create_and_get(tmp_db_path):
    fid = repo.create_folder(name="平台经营", created_by=1)
    assert fid > 0
    f = repo.get_folder(fid)
    assert f["name"] == "平台经营"
    assert f["parent_id"] is None
    assert f["sort_order"] == 0
    assert f["created_by"] == 1
    assert f["created_at"]  # 默认时间戳


def test_folder_nested_and_list_order(tmp_db_path):
    a = repo.create_folder(name="A", created_by=1, sort_order=1)
    repo.create_folder(name="B", created_by=1, sort_order=0)
    repo.create_folder(name="A-child", created_by=1, parent_id=a, sort_order=0)
    folders = repo.list_folders()
    assert len(folders) == 3
    # 按 sort_order 排：B(0) 在 A(1) 前
    top = [f for f in folders if f["parent_id"] is None]
    assert [f["name"] for f in top] == ["B", "A"]
    child = [f for f in folders if f["parent_id"] == a]
    assert child[0]["name"] == "A-child"


def test_folder_update_rename_move_reorder(tmp_db_path):
    root = repo.create_folder(name="root", created_by=1)
    fid = repo.create_folder(name="old", created_by=1)
    repo.update_folder(fid, name="new", parent_id=root, sort_order=5)
    f = repo.get_folder(fid)
    assert f["name"] == "new" and f["parent_id"] == root and f["sort_order"] == 5
    # _UNSET 语义：只改 sort_order，parent_id 不动
    repo.update_folder(fid, sort_order=9)
    assert repo.get_folder(fid)["parent_id"] == root
    # 显式移到顶层（parent_id=None，区别于 _UNSET 不改）
    repo.update_folder(fid, parent_id=None)
    assert repo.get_folder(fid)["parent_id"] is None


def test_folder_delete(tmp_db_path):
    fid = repo.create_folder(name="tmp", created_by=1)
    repo.delete_folder(fid)
    assert repo.get_folder(fid) is None


# ─── bi_reports ──────────────────────────────────────────────────────────────

def test_report_create_and_get(tmp_db_path):
    rid = repo.create_report(
        title="平台日汇总·宽表", sql_text="SELECT dt AS 日期 FROM dwd_daily",
        created_by=1, data_source_id=3, column_config='{"日期":{"frozen":true}}',
    )
    assert rid > 0
    r = repo.get_report(rid)
    assert r["title"] == "平台日汇总·宽表"
    assert r["report_type"] == "wide_table"  # 默认
    assert r["sql_text"] == "SELECT dt AS 日期 FROM dwd_daily"
    assert r["data_source_id"] == 3
    assert r["column_config"] == '{"日期":{"frozen":true}}'
    assert r["folder_id"] is None       # 未归档默认
    assert r["refresh_seq"] == 0
    assert r["last_run_rows_json"] is None
    assert r["created_by"] == 1


def test_report_list_order_by_folder_then_sort(tmp_db_path):
    f = repo.create_folder(name="f", created_by=1)
    repo.create_report(title="unfiled", sql_text="SELECT 1", created_by=1)  # folder NULL
    repo.create_report(title="in-folder-2", sql_text="SELECT 1", created_by=1, folder_id=f, sort_order=2)
    repo.create_report(title="in-folder-1", sql_text="SELECT 1", created_by=1, folder_id=f, sort_order=1)
    titles = [r["title"] for r in repo.list_reports()]
    # NULL folder 排最前（SQLite NULL ASC 优先），folder 内按 sort_order
    assert titles == ["unfiled", "in-folder-1", "in-folder-2"]


def test_report_update_move_to_unfiled_via_null(tmp_db_path):
    f = repo.create_folder(name="f", created_by=1)
    rid = repo.create_report(title="t", sql_text="SELECT 1", created_by=1, folder_id=f)
    assert repo.get_report(rid)["folder_id"] == f
    # 只改 title，folder_id 不动（_UNSET）
    repo.update_report(rid, title="t2")
    assert repo.get_report(rid)["folder_id"] == f and repo.get_report(rid)["title"] == "t2"
    # 显式移到未归档（folder_id=None）
    repo.update_report(rid, folder_id=None)
    assert repo.get_report(rid)["folder_id"] is None


def test_report_update_sql_and_configs(tmp_db_path):
    rid = repo.create_report(title="t", sql_text="SELECT 1", created_by=1)
    repo.update_report(rid, sql_text="SELECT 2", column_config='{"a":1}',
                       overlay_config='[{"row_index":0,"col":"a","kind":"formula","value":"=SUM(A1:A2)"}]')
    r = repo.get_report(rid)
    assert r["sql_text"] == "SELECT 2"
    assert r["column_config"] == '{"a":1}'
    assert "SUM(A1:A2)" in r["overlay_config"]
    # 显式清空 overlay（None）
    repo.update_report(rid, overlay_config=None)
    assert repo.get_report(rid)["overlay_config"] is None


def test_report_update_last_run_bumps_refresh_seq(tmp_db_path):
    rid = repo.create_report(title="t", sql_text="SELECT 1", created_by=1)
    repo.update_last_run(rid, rows_json='[{"a":1}]', truncated=0, elapsed_ms=12,
                         run_at="2026-07-07 09:00:00", last_run_by=1)
    r = repo.get_report(rid)
    assert r["last_run_rows_json"] == '[{"a":1}]'
    assert r["last_run_ms"] == 12
    assert r["last_run_at"] == "2026-07-07 09:00:00"
    assert r["last_run_by"] == 1
    assert r["refresh_seq"] == 1   # bump
    # 二次刷新 → seq=2
    repo.update_last_run(rid, rows_json='[]', truncated=0, elapsed_ms=5,
                         run_at="2026-07-07 10:00:00", last_run_by=None)
    assert repo.get_report(rid)["refresh_seq"] == 2


def test_report_delete(tmp_db_path):
    rid = repo.create_report(title="t", sql_text="SELECT 1", created_by=1)
    repo.delete_report(rid)
    assert repo.get_report(rid) is None
