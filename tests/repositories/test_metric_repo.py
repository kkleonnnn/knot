"""tests/repositories/test_metric_repo — v0.7.0 C1 指标注册表地基守护测试（TDD）。

覆盖：
- OOS-1 死线：metrics 表 0 tenant_id/project_id（14 列契约）+ create/update 拒 tenant_id/project_id 注入
- metric_repo CRUD（create/get/list/update/delete）+ name+caliber 必填
- per-catalog name 唯一（UNIQUE(catalog_id, name)）+ 不同 catalog 同名 OK + list_metrics(catalog_id) 过滤
- lineage v0.7.0 inert 存储（不解析/不校验内容；自引用/循环 DFS 校验留 v0.7.1 编译时）
"""
import sqlite3

import pytest

from knot.models.errors import MetadataError
from knot.repositories import metric_repo
from knot.repositories.base import get_conn


# ─── OOS-1 死线：0 tenant_id/project_id ──────────────────────────────

def test_metrics_schema_no_tenant(tmp_db_path):
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metrics)").fetchall()}
    conn.close()
    assert "tenant_id" not in cols and "project_id" not in cols, (
        "OOS-1 死线：metrics 严禁 tenant_id/project_id（catalog_id = 水平切分非租户）"
    )
    assert cols == {
        "id", "catalog_id", "name", "display", "aliases", "caliber", "base_object",
        "filters", "dimensions", "lineage", "freshness_lag_days", "enabled",
        "created_at", "updated_at",
    }


def test_create_rejects_tenant_id(tmp_db_path):
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)", tenant_id=42)


def test_update_rejects_project_id(tmp_db_path):
    mid = metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    with pytest.raises(MetadataError):
        metric_repo.update_metric(mid, project_id=7)


# ─── CRUD ────────────────────────────────────────────────────────────

def test_create_get_metric(tmp_db_path):
    mid = metric_repo.create_metric(
        catalog_id=1, name="gmv", display="成交额 GMV", caliber="SUM(o.pay_amount)",
        aliases='["成交额","gmv"]', dimensions='["date","city"]',
    )
    m = metric_repo.get_metric(mid)
    assert m["name"] == "gmv"
    assert m["caliber"] == "SUM(o.pay_amount)"
    assert m["display"] == "成交额 GMV"
    assert m["catalog_id"] == 1
    assert m["enabled"] == 1            # default
    assert m["freshness_lag_days"] == 1  # default


def test_create_requires_name_and_caliber(tmp_db_path):
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="gmv")  # 缺 caliber


def test_update_metric_whitelist(tmp_db_path):
    mid = metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    metric_repo.update_metric(mid, caliber="SUM(o.pay_amount)", display="GMV")
    m = metric_repo.get_metric(mid)
    assert m["caliber"] == "SUM(o.pay_amount)"
    assert m["display"] == "GMV"


def test_delete_metric(tmp_db_path):
    mid = metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    metric_repo.delete_metric(mid)
    assert metric_repo.get_metric(mid) is None


# ─── per-catalog name 唯一 + list 过滤 ───────────────────────────────

def test_per_catalog_name_unique(tmp_db_path):
    metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    with pytest.raises(sqlite3.IntegrityError):
        metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.other)")


def test_same_name_different_catalog_ok(tmp_db_path):
    metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    mid2 = metric_repo.create_metric(catalog_id=2, name="gmv", caliber="SUM(o.amt2)")
    assert metric_repo.get_metric(mid2)["catalog_id"] == 2


def test_list_metrics_by_catalog(tmp_db_path):
    metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    metric_repo.create_metric(catalog_id=2, name="dau", caliber="COUNT(DISTINCT u.id)")
    assert len(metric_repo.list_metrics()) == 2          # 全部
    c1 = metric_repo.list_metrics(catalog_id=1)
    assert len(c1) == 1 and c1[0]["name"] == "gmv"


# ─── lineage inert（v0.7.0 不校验内容；DFS 校验留 v0.7.1）────────────

def test_lineage_inert_stored_unparsed(tmp_db_path):
    # v0.7.0 lineage 仅 inert 存储 — 任意 JSON（含派生依赖）照存不解析/不校验（DFS 留 v0.7.1）
    mid = metric_repo.create_metric(
        catalog_id=1, name="arpu", caliber="gmv / dau", lineage='["gmv","dau"]',
    )
    assert metric_repo.get_metric(mid)["lineage"] == '["gmv","dau"]'
