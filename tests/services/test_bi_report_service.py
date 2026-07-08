"""tests/services/test_bi_report_service.py — v0.8.5 (②a) BI 报表 service 编排。

覆盖：SQL 存前只读预校验(D7)/title sanitize/to_dto 脱敏(R-BI-6)/文件夹删 reparent/
refresh 无引擎不写 + 成功写快照 bump refresh_seq(D6)/缺报表返 None。
"""
import pytest

from knot.repositories import bi_report_repo as repo
from knot.services import bi_report_service as svc

_ADMIN = {"id": 1, "role": "admin"}


def test_create_validates_and_persists(tmp_db_path):
    r = svc.create_report(_ADMIN, title="日汇总", sql_text="SELECT dt AS 日期 FROM t")
    assert r["id"] > 0 and r["title"] == "日汇总" and r["report_type"] == "wide_table"


def test_create_rejects_write_sql(tmp_db_path):
    for bad in ("DELETE FROM users", "UPDATE t SET a=1", "DROP TABLE t"):
        with pytest.raises(svc.SqlNotReadOnly):
            svc.create_report(_ADMIN, title="x", sql_text=bad)
    assert svc.list_all() == []  # 无报表落库


def test_create_title_sanitized(tmp_db_path):
    assert svc.create_report(_ADMIN, title="   ", sql_text="SELECT 1")["title"] == "未命名报表"


def test_update_rejects_write_sql_keeps_old(tmp_db_path):
    r = svc.create_report(_ADMIN, title="t", sql_text="SELECT 1")
    with pytest.raises(svc.SqlNotReadOnly):
        svc.update_report(r["id"], sql_text="DROP TABLE t")
    assert svc.get_report(r["id"])["sql_text"] == "SELECT 1"  # 未改


def test_to_dto_strips_sql_for_non_admin(tmp_db_path):
    r = svc.create_report(_ADMIN, title="t", sql_text="SELECT secret FROM t",
                          column_config={"日期": {"frozen": True}})
    assert "sql_text" in svc.to_dto(r, is_admin=True)
    dto = svc.to_dto(r, is_admin=False)
    assert "sql_text" not in dto and dto["title"] == "t"
    assert dto["column_config"] == r["column_config"]  # 列配置（展示层）保留


def test_delete_folder_reparents(tmp_db_path):
    parent = svc.create_folder(_ADMIN, name="p")
    child = svc.create_folder(_ADMIN, name="c", parent_id=parent["id"])
    rpt = svc.create_report(_ADMIN, title="r", sql_text="SELECT 1", folder_id=parent["id"])
    assert svc.delete_folder(parent["id"]) is True
    assert repo.get_folder(parent["id"]) is None
    assert svc.get_report(rpt["id"])["folder_id"] is None            # 报表 → 未归档
    assert repo.get_folder(child["id"])["parent_id"] is None          # 子文件夹 → 顶层


def test_refresh_no_engine_returns_error_no_write(tmp_db_path):
    r = svc.create_report(_ADMIN, title="t", sql_text="SELECT 1")  # data_source_id None
    out = svc.refresh(r["id"], _ADMIN)
    assert out["error"] and out["rows"] == []
    assert svc.get_report(r["id"])["refresh_seq"] == 0            # 无 engine 不写


def test_refresh_success_writes_snapshot_and_bumps_seq(tmp_db_path, monkeypatch):
    r = svc.create_report(_ADMIN, title="t", sql_text="SELECT 1", data_source_id=7)
    monkeypatch.setattr(svc.engine_cache, "get_engine_for_source", lambda sid: object())
    monkeypatch.setattr(svc.db_connector, "execute_query", lambda eng, sql, **kw: ([{"a": 1}, {"a": 2}], None))
    out = svc.refresh(r["id"], _ADMIN)
    assert out["error"] == "" and len(out["rows"]) == 2
    saved = svc.get_report(r["id"])
    assert saved["refresh_seq"] == 1 and saved["last_run_by"] == 1
    assert "1" in saved["last_run_rows_json"] and "2" in saved["last_run_rows_json"]


def test_refresh_missing_report_returns_none(tmp_db_path):
    assert svc.refresh(9999, _ADMIN) is None


# ── ②b 仪表盘 tile（diff-by-id / B-1 归属 / B-2 脱敏 / 级联删）─────────────────────

def _dash_with_tiles(tiles):
    return svc.create_report(_ADMIN, title="仪表盘", sql_text="SELECT 1",
                             report_type="dashboard", tiles=tiles)


def test_create_with_tiles_persists_and_validates(tmp_db_path):
    r = _dash_with_tiles([
        {"tile_type": "kpi", "title": "今日量", "sql_text": "SELECT sum(v) FROM t", "grid_span": 1},
        {"tile_type": "line", "title": "趋势", "sql_text": "SELECT d, v FROM t", "sort_order": 1},
    ])
    tiles = r["tiles"]
    assert [t["title"] for t in tiles] == ["今日量", "趋势"]
    assert tiles[0]["tile_type"] == "kpi" and tiles[1]["tile_type"] == "line"


def test_create_tile_rejects_write_sql(tmp_db_path):
    with pytest.raises(svc.SqlNotReadOnly):
        _dash_with_tiles([{"tile_type": "kpi", "sql_text": "DELETE FROM t"}])


def test_to_dto_strips_per_tile_sql_and_no_mutation(tmp_db_path):
    """B-2：非 admin 报表级 + 每 tile 都无 sql_text；且脱敏不 mutate 原 dict（admin 仍见 SQL）。"""
    r = _dash_with_tiles([{"tile_type": "kpi", "sql_text": "SELECT secret FROM t"}])
    full = svc.get_report(r["id"])
    dto = svc.to_dto(full, is_admin=False)
    assert "sql_text" not in dto
    assert all("sql_text" not in t for t in dto["tiles"])
    # B-2b：深拷 → 原 full.tiles 未被 mutate（同进程 admin 路径不受污染）
    assert full["tiles"][0]["sql_text"] == "SELECT secret FROM t"
    admin_dto = svc.to_dto(svc.get_report(r["id"]), is_admin=True)
    assert admin_dto["tiles"][0]["sql_text"] == "SELECT secret FROM t"


def test_update_diff_by_id_preserves_snapshot_inserts_deletes(tmp_db_path):
    from knot.repositories import bi_report_tile_repo as trepo
    r = _dash_with_tiles([
        {"tile_type": "kpi", "title": "keep", "sql_text": "SELECT 1"},
        {"tile_type": "kpi", "title": "drop", "sql_text": "SELECT 2"},
    ])
    keep_id = r["tiles"][0]["id"]
    trepo.update_tile_last_run(keep_id, rows_json='[{"v":9}]', truncated=0, elapsed_ms=4,
                               run_at="t", error=None)
    svc.update_report(r["id"], admin=_ADMIN, tiles=[
        {"id": keep_id, "tile_type": "kpi", "title": "keep2", "sql_text": "SELECT 1"},
        {"tile_type": "line", "title": "add", "sql_text": "SELECT 3"},
    ])
    tiles = svc.get_report(r["id"])["tiles"]
    assert sorted(t["title"] for t in tiles) == ["add", "keep2"]     # drop 删、add 插
    keep = next(t for t in tiles if t["id"] == keep_id)
    assert keep["title"] == "keep2"
    assert keep["last_run_rows_json"] == '[{"v":9}]'                 # §5#7 快照未 wipe


def test_update_tile_id_ownership_guard(tmp_db_path):
    """B-1：payload tile id ∉ 本 report → 忽略，绝不改他报表 tile、不并入本表。"""
    from knot.repositories import bi_report_tile_repo as trepo
    other = _dash_with_tiles([{"tile_type": "kpi", "title": "他表", "sql_text": "SELECT 1"}])
    other_tid = other["tiles"][0]["id"]
    target = _dash_with_tiles([{"tile_type": "kpi", "title": "本表", "sql_text": "SELECT 2"}])
    svc.update_report(target["id"], admin=_ADMIN, tiles=[
        {"id": other_tid, "tile_type": "kpi", "title": "越权改", "sql_text": "SELECT 9"},
        {"id": target["tiles"][0]["id"], "tile_type": "kpi", "title": "本表2", "sql_text": "SELECT 2"},
    ])
    assert trepo.get_tile(other_tid)["title"] == "他表"             # 他表 tile 未被动
    assert [t["title"] for t in svc.get_report(target["id"])["tiles"]] == ["本表2"]  # 越权 id 忽略


def test_delete_report_cascades_tiles(tmp_db_path):
    from knot.repositories import bi_report_tile_repo as trepo
    r = _dash_with_tiles([{"tile_type": "kpi", "sql_text": "SELECT 1"}])
    assert len(trepo.list_by_report(r["id"])) == 1
    assert svc.delete_report(r["id"]) is True
    assert trepo.list_by_report(r["id"]) == []                      # 无孤儿


def test_tabbed_report_reuses_tile_path(tmp_db_path, monkeypatch):
    """v0.8.7：report_type='tabbed' 复用 tile 后端 —— create+tiles / refresh 走 _refresh_tiled / 脱敏。"""
    r = svc.create_report(_ADMIN, title="运营日报", sql_text="SELECT 1", report_type="tabbed",
                          data_source_id=7, tiles=[
                              {"tile_type": "table", "title": "日汇总", "sql_text": "SELECT * FROM d"},
                              {"tile_type": "table", "title": "周汇总", "sql_text": "SELECT * FROM w"},
                          ])
    assert r["report_type"] == "tabbed" and [t["title"] for t in r["tiles"]] == ["日汇总", "周汇总"]
    monkeypatch.setattr(svc.engine_cache, "get_engine_for_source", lambda sid: object())
    monkeypatch.setattr(svc.db_connector, "execute_query", lambda eng, sql, **kw: ([{"统计周期": "2026-07-07"}], None))
    out = svc.refresh(r["id"], _ADMIN)
    assert out["report_type"] == "tabbed" and out["tile_count"] == 2 and out["error_count"] == 0
    # 非 admin 每页无 sql_text（复用 tile to_dto 脱敏）
    dto = svc.to_dto(svc.get_report(r["id"]), is_admin=False)
    assert all("sql_text" not in t for t in dto["tiles"])


def test_dashboard_refresh_no_engine_preserves_tile_snapshots(tmp_db_path):
    """复核修：engine None（DB blip / 无数据源）→ 不抹 tile 快照、不 bump（镜像 wide_table 早返）。"""
    from knot.repositories import bi_report_tile_repo as trepo
    r = _dash_with_tiles([{"tile_type": "kpi", "sql_text": "SELECT 1"}])   # 无 data_source → engine None
    tid = r["tiles"][0]["id"]
    trepo.update_tile_last_run(tid, rows_json='[{"v":1}]', truncated=0, elapsed_ms=3, run_at="t", error=None)
    before_seq = svc.get_report(r["id"])["refresh_seq"]
    out = svc.refresh(r["id"], _ADMIN)
    assert out["error"]                                             # 返引擎错
    assert trepo.get_tile(tid)["last_run_rows_json"] == '[{"v":1}]'  # 上次 good 快照保留（未抹空）
    assert svc.get_report(r["id"])["refresh_seq"] == before_seq      # 不 bump


# ── v0.8.8 ③ reorder + ② 行上限 ─────────────────────────────────────────────────

def test_reorder_reports_assigns_sort_order(tmp_db_path):
    a = svc.create_report(_ADMIN, title="A", sql_text="SELECT 1")["id"]
    b = svc.create_report(_ADMIN, title="B", sql_text="SELECT 1")["id"]
    c = svc.create_report(_ADMIN, title="C", sql_text="SELECT 1")["id"]
    svc.reorder_reports([c, a, b])
    order = {r["id"]: r["sort_order"] for r in repo.list_reports()}
    assert (order[c], order[a], order[b]) == (0, 1, 2)
    assert [r["id"] for r in repo.list_reports()] == [c, a, b]   # list 按 sort_order


def test_reorder_reports_missing_id_noop(tmp_db_path):
    a = svc.create_report(_ADMIN, title="A", sql_text="SELECT 1")["id"]
    svc.reorder_reports([999999, a])                             # 不存在 id → no-op；a 得 sort_order=1
    assert svc.get_report(a)["sort_order"] == 1


def test_reorder_folders_assigns_sort_order(tmp_db_path):
    f1 = svc.create_folder(_ADMIN, name="F1")["id"]
    f2 = svc.create_folder(_ADMIN, name="F2")["id"]
    svc.reorder_folders([f2, f1])
    assert [f["id"] for f in repo.list_folders()] == [f2, f1]


def test_reorder_empty_noop(tmp_db_path):
    svc.reorder_reports([])                                       # 空列表不炸
    svc.reorder_folders([])


def test_exec_one_caps_at_10000_and_passes_max_rows(tmp_db_path, monkeypatch):
    seen = {}

    def _exec(eng, sql, **kw):
        seen["max_rows"] = kw.get("max_rows")
        return ([{"a": i} for i in range(svc._LAST_RUN_ROW_LIMIT + 5)], None)

    monkeypatch.setattr(svc.db_connector, "execute_query", _exec)
    snap, truncated, _ms, err = svc._exec_one(object(), "SELECT a FROM t")
    assert svc._LAST_RUN_ROW_LIMIT == 10000                      # ② kk：全量展示上限
    assert seen["max_rows"] == 10000                             # 透传查询层（无 LIMIT 的 SQL → LIMIT 10000）
    assert truncated is True and len(snap) == 10000 and err == ""


def test_exec_one_under_limit_not_truncated(tmp_db_path, monkeypatch):
    monkeypatch.setattr(svc.db_connector, "execute_query",
                        lambda eng, sql, **kw: ([{"a": 1}] * 500, None))
    snap, truncated, _ms, _err = svc._exec_one(object(), "SELECT a FROM t")
    assert truncated is False and len(snap) == 500               # 数百行（真运营日报量级）全显不截
