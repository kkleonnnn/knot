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
    monkeypatch.setattr(svc.db_connector, "execute_query", lambda eng, sql: ([{"a": 1}, {"a": 2}], None))
    out = svc.refresh(r["id"], _ADMIN)
    assert out["error"] == "" and len(out["rows"]) == 2
    saved = svc.get_report(r["id"])
    assert saved["refresh_seq"] == 1 and saved["last_run_by"] == 1
    assert "1" in saved["last_run_rows_json"] and "2" in saved["last_run_rows_json"]


def test_refresh_missing_report_returns_none(tmp_db_path):
    assert svc.refresh(9999, _ADMIN) is None
