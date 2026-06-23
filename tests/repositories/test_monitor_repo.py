"""tests/repositories/test_monitor_repo.py — v0.7.7 C1 semantic_monitors CRUD + 触发留痕守护。

OOS-1 死线（0 tenant_id/project_id）+ catalog 隔离 + CRUD + trigger append-only（R-SL-67/75）。
"""
import sqlite3

import pytest

from knot.models.errors import MetadataError
from knot.repositories import monitor_repo as mr


def _mk(**kw):
    base = dict(name="gmv 异动", metric_name="gmv", comparator="pct_change_lt", threshold=-20.0,
                baseline_period="last_period", time_window="today",
                action_type="webhook", action_target="https://hooks.example.com/y")
    base.update(kw)
    return base


def test_schema_no_tenant_and_has_catalog_id(tmp_db_path):
    conn = sqlite3.connect(tmp_db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(semantic_monitors)").fetchall()}
    conn.close()
    assert "tenant_id" not in cols and "project_id" not in cols          # OOS-1 死线
    assert {"catalog_id", "metric_name", "comparator", "threshold", "action_target"} <= cols


def test_create_list_get_update_delete(tmp_db_path):
    mid = mr.create_monitor(catalog_id=1, **_mk())
    m = mr.get_monitor(mid)
    assert m["metric_name"] == "gmv" and m["comparator"] == "pct_change_lt" and m["enabled"] == 1
    mr.update_monitor(mid, threshold=-30.0, enabled=0)
    assert mr.get_monitor(mid)["threshold"] == -30.0 and mr.get_monitor(mid)["enabled"] == 0
    assert len(mr.list_monitors(catalog_id=1)) == 1
    assert mr.list_monitors(catalog_id=1, enabled_only=True) == []        # enabled=0 → 不返
    mr.delete_monitor(mid)
    assert mr.get_monitor(mid) is None


def test_catalog_isolation(tmp_db_path):
    mr.create_monitor(catalog_id=1, **_mk(name="a"))
    mr.create_monitor(catalog_id=2, **_mk(name="b"))
    assert len(mr.list_monitors(catalog_id=1)) == 1                       # OOS-1 隔离
    assert len(mr.list_monitors(catalog_id=2)) == 1
    assert len(mr.list_monitors()) == 2                                   # None → 全部


def test_oos1_reject_tenant(tmp_db_path):
    with pytest.raises(MetadataError):
        mr.create_monitor(catalog_id=1, tenant_id=5, **_mk())            # OOS-1 死锁


def test_required_fields(tmp_db_path):
    with pytest.raises(MetadataError):
        mr.create_monitor(catalog_id=1, name="x")                        # 缺 metric_name/comparator/threshold


def test_trigger_audit_append_only(tmp_db_path):
    mid = mr.create_monitor(catalog_id=1, **_mk())
    mr.create_trigger(mid, catalog_id=1, metric_value=-25.0, hit=1, status="fired", detail="webhook ok")
    mr.create_trigger(mid, catalog_id=1, metric_value=-5.0, hit=0, status="no_hit")
    rows = mr.list_triggers(mid)
    assert len(rows) == 2 and rows[0]["status"] == "no_hit"              # id DESC 最近优先
    assert rows[1]["hit"] == 1 and rows[1]["status"] == "fired"
