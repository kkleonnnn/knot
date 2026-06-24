"""tests/repositories/test_metric_repo — v0.7.0 C1 指标注册表地基守护测试（TDD）。

覆盖：
- OOS-1 死线：metrics 表 0 tenant_id/project_id（15 列契约 — v0.7.17 +date_column）+ create/update 拒 tenant_id/project_id 注入
- metric_repo CRUD（create/get/list/update/delete）+ name+caliber 必填
- per-catalog name 唯一（UNIQUE(catalog_id, name)）+ 不同 catalog 同名 OK + list_metrics(catalog_id) 过滤
- lineage v0.7.16 激活：结构化派生定义 {op∈白名单,left,right} 形状校验（`_validate_lineage`）；
  派生 metric 免 caliber；deps 原子/单层防循环留编译时（compiler）—— repo 仅校验形状
- date_column v0.7.17：时间窗注入列名（显式优先，空=regex 推断）；CRUD 透传（repo 不校验列存在性）
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
        "filters", "dimensions", "date_column", "lineage", "freshness_lag_days", "enabled",
        "created_at", "updated_at",
    }   # v0.7.17 +date_column（14→15）


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


# ─── lineage v0.7.16 派生定义形状校验（_validate_lineage）────────────

def test_derived_lineage_stored(tmp_db_path):
    # v0.7.16：派生 metric lineage = 结构化 {op,left,right}，照存（编译时再解析 deps）
    lin = '{"op":"divide","left":"gmv","right":"dau"}'
    mid = metric_repo.create_metric(catalog_id=1, name="arpu", lineage=lin)   # 派生免 caliber
    assert metric_repo.get_metric(mid)["lineage"] == lin


def test_derived_metric_exempt_from_caliber(tmp_db_path):
    # 派生（有 lineage）免 caliber；原子（无 lineage）须 caliber
    mid = metric_repo.create_metric(catalog_id=1, name="arpu",
                                    lineage='{"op":"multiply","left":"a","right":"b"}')
    assert metric_repo.get_metric(mid)["caliber"] == ""          # 派生无 caliber


def test_create_no_caliber_no_lineage_raises(tmp_db_path):
    # 既无 caliber 又无 lineage → MetadataError（原子须 caliber / 派生须 lineage）
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="bad")


def test_lineage_bad_op_rejected(tmp_db_path):
    # op ∉ 白名单（divide/multiply/add/subtract）→ MetadataError（形状校验）
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="x",
                                  lineage='{"op":"powerrr","left":"a","right":"b"}')


def test_lineage_missing_operand_rejected(tmp_db_path):
    # lineage 缺 left/right → MetadataError
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="x", lineage='{"op":"divide","left":"a"}')


def test_lineage_non_json_rejected(tmp_db_path):
    # lineage 非合法 JSON → MetadataError（旧 inert list '["gmv","dau"]' 在 v0.7.16 也属非派生定义被拒）
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="x", caliber="SUM(o.a)", lineage="not json")
    with pytest.raises(MetadataError):
        metric_repo.create_metric(catalog_id=1, name="y", caliber="SUM(o.a)", lineage='["gmv","dau"]')


# ─── date_column v0.7.17：时间窗注入列名 CRUD 透传 ────────────────────

def test_date_column_stored_and_updated(tmp_db_path):
    # 显式 date_column 照存（repo 不校验列存在性 — 跨层校验 defer，同 lineage）
    mid = metric_repo.create_metric(catalog_id=1, name="deposit", caliber="SUM(o.deposit)",
                                    base_object="ohx_ads.ads_operation_report_daily", date_column="sta_date")
    assert metric_repo.get_metric(mid)["date_column"] == "sta_date"
    metric_repo.update_metric(mid, date_column="biz_date")
    assert metric_repo.get_metric(mid)["date_column"] == "biz_date"


def test_date_column_defaults_empty(tmp_db_path):
    # 未声明 date_column → 空串（= regex fallback；不破存量）
    mid = metric_repo.create_metric(catalog_id=1, name="gmv", caliber="SUM(o.amt)")
    assert metric_repo.get_metric(mid)["date_column"] == ""
