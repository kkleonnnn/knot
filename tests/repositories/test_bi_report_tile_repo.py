"""tests/repositories/test_bi_report_tile_repo.py — v0.8.6 (②b) 仪表盘 tile CRUD。

覆盖：create/get/list(order) · update(改配置/排序/跨度) **不 wipe 快照** ·
update_tile_last_run(per-tile 快照+error) · delete · delete_by_report(级联) ·
bi_report_repo.touch_refresh_seq(bump-only 不碰报表级 rows)。
R-BI-1：全新表，与 saved_reports 0 交集。
"""
from knot.repositories import bi_report_repo as rrepo
from knot.repositories import bi_report_tile_repo as trepo


def _report(dash=True):
    return rrepo.create_report(
        title="仪表盘", sql_text="SELECT 1", created_by=1,
        report_type="dashboard" if dash else "wide_table",
    )


def test_create_get_list_order(tmp_db_path):
    rid = _report()
    a = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 1", created_by=1, title="A", sort_order=1)
    b = trepo.create_tile(rid, tile_type="line", sql_text="SELECT 2", created_by=1, title="B", sort_order=0)
    assert a > 0 and b > 0
    t = trepo.get_tile(a)
    assert t["tile_type"] == "kpi" and t["title"] == "A" and t["grid_span"] == 1 and t["report_id"] == rid
    tiles = trepo.list_by_report(rid)
    # 按 sort_order 排：B(0) 在 A(1) 前
    assert [x["title"] for x in tiles] == ["B", "A"]


def test_update_does_not_wipe_snapshot(tmp_db_path):
    """B-2/§5#7 correctness：改 tile 配置/排序/跨度绝不清 last_run_*。"""
    rid = _report()
    tid = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 1", created_by=1)
    trepo.update_tile_last_run(tid, rows_json='[{"v":1}]', truncated=0, elapsed_ms=5,
                               run_at="2026-07-08 10:00:00", error=None)
    # 改配置 + 排序 + 跨度
    trepo.update_tile(tid, tile_type="line", title="改了", sql_text="SELECT 9",
                      sort_order=3, grid_span=2)
    t = trepo.get_tile(tid)
    assert t["tile_type"] == "line" and t["title"] == "改了" and t["sql_text"] == "SELECT 9"
    assert t["sort_order"] == 3 and t["grid_span"] == 2
    # 快照原样保留
    assert t["last_run_rows_json"] == '[{"v":1}]'
    assert t["last_run_ms"] == 5 and t["last_run_at"] == "2026-07-08 10:00:00"


def test_update_tile_last_run_per_tile_error(tmp_db_path):
    rid = _report()
    ok = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 1", created_by=1)
    bad = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 2", created_by=1)
    trepo.update_tile_last_run(ok, rows_json="[]", truncated=0, elapsed_ms=3, run_at="t", error=None)
    trepo.update_tile_last_run(bad, rows_json="[]", truncated=0, elapsed_ms=0, run_at="t", error="表不存在")
    # 一 tile 挂不连累另一 tile
    assert trepo.get_tile(ok)["last_run_error"] is None
    assert trepo.get_tile(bad)["last_run_error"] == "表不存在"


def test_update_title_unset_vs_null(tmp_db_path):
    rid = _report()
    tid = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 1", created_by=1, title="orig")
    trepo.update_tile(tid, sort_order=2)                 # 不传 title → _UNSET 不改
    assert trepo.get_tile(tid)["title"] == "orig"
    trepo.update_tile(tid, title=None)                   # 显式 None → 置 NULL
    assert trepo.get_tile(tid)["title"] is None


def test_delete_and_cascade(tmp_db_path):
    rid = _report()
    t1 = trepo.create_tile(rid, tile_type="kpi", sql_text="SELECT 1", created_by=1)
    trepo.create_tile(rid, tile_type="line", sql_text="SELECT 2", created_by=1)
    trepo.delete_tile(t1)
    assert len(trepo.list_by_report(rid)) == 1
    trepo.delete_by_report(rid)
    assert trepo.list_by_report(rid) == []


def test_touch_refresh_seq_bump_only(tmp_db_path):
    """B-3：touch_refresh_seq 只 bump 报表级 refresh_seq，绝不写 last_run_rows_json。"""
    rid = _report()
    before = rrepo.get_report(rid)
    assert before["refresh_seq"] == 0 and before["last_run_rows_json"] is None
    rrepo.touch_refresh_seq(rid)
    rrepo.touch_refresh_seq(rid)
    after = rrepo.get_report(rid)
    assert after["refresh_seq"] == 2
    assert after["last_run_rows_json"] is None            # dashboard 报表级 rows 保持空（S3 自洽）
