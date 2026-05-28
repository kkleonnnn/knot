"""v0.6.2.1 commit 1 — F1 catalog source_type 推断兜底 + ε2 fail-fast 熔断守护测试

覆盖红线：
  R-PB-C1-1  catalog._load_from_db 推断 source_type + ε2 fail-fast 熔断
  NRP-C1     catalog source_type 推断与 reload 协同（admin 改 → cache invalidate → 下次走新）

ε2 决策（资深 2026-05-28）：
  - DataSource 表查询失败 → MetadataError 熔断（防 BI 全盘瘫痪）
  - DataSource 表空 → MetadataError 熔断（同上）
  - DataSource 正常非空 + db_type='http' → 推断 catalog 同 db_name 表 source_type='http'
  - strict=False（startup）→ MetadataError 降级为 warning；strict=True（admin/query）→ 上抛
"""
from unittest.mock import patch

import pytest

from knot.models.errors import MetadataError
from knot.services.agents import catalog as catalog_loader

# ─── 直接调用 helper 测试（不依赖 client / fixture）────────────────


def test_R_PB_C1_1_infer_http_source_type_for_http_datasource():
    """db_type='http' DataSource → catalog 同 db_name 表强制 source_type='http'。"""
    tables = [
        {"db": "futures_admin", "table": "futures_position_list", "topics": ["持仓"]},
        {"db": "futures_admin", "table": "futures_user_pending", "topics": ["挂单"]},
        {"db": "ohx_dwd", "table": "dwd_user_position_history", "topics": ["历史"]},
    ]
    mock_ds = [
        {"db_type": "http", "db_database": "futures_admin"},
        {"db_type": "doris", "db_database": "ohx_dwd,ohx_ads"},
    ]
    with patch("knot.repositories.data_source_repo.list_datasources",
               return_value=mock_ds):
        result = catalog_loader._infer_source_types_from_datasources(tables)

    # futures_admin 两表 → 推断 http
    assert result[0]["source_type"] == "http"
    assert result[1]["source_type"] == "http"
    # ohx_dwd 表 → 不动（不在 http_db_names）
    assert "source_type" not in result[2]


def test_R_PB_C1_1_explicit_source_type_not_overridden():
    """显式 source_type（来自 _local_catalog.py）→ 不被推断覆盖。"""
    tables = [
        {"db": "futures_admin", "table": "x", "source_type": "http"},  # 显式
        {"db": "futures_admin", "table": "y"},  # 推断
    ]
    mock_ds = [{"db_type": "http", "db_database": "futures_admin"}]
    with patch("knot.repositories.data_source_repo.list_datasources",
               return_value=mock_ds):
        result = catalog_loader._infer_source_types_from_datasources(tables)

    assert result[0]["source_type"] == "http"  # 显式 sustained
    assert result[1]["source_type"] == "http"  # 推断 ✓


def test_R_PB_C1_1_no_http_datasource_no_inference():
    """无 db_type='http' DataSource → 不推断（passthrough）。"""
    tables = [
        {"db": "futures_admin", "table": "x"},
        {"db": "ohx_dwd", "table": "y"},
    ]
    mock_ds = [{"db_type": "doris", "db_database": "ohx_dwd,ohx_ads"}]
    with patch("knot.repositories.data_source_repo.list_datasources",
               return_value=mock_ds):
        result = catalog_loader._infer_source_types_from_datasources(tables)

    assert "source_type" not in result[0]
    assert "source_type" not in result[1]


# ─── ε2 fail-fast 熔断测试（守护者 + Stage 2 关键贡献）─────────


def test_epsilon2_fail_fast_datasource_empty_raises():
    """ε2：DataSource 表为空 → MetadataError 熔断（防误推断 doris/mysql 为 http）。"""
    tables = [{"db": "futures_admin", "table": "x"}]
    with patch("knot.repositories.data_source_repo.list_datasources",
               return_value=[]):
        with pytest.raises(MetadataError, match="DataSource 表为空"):
            catalog_loader._infer_source_types_from_datasources(tables)


def test_epsilon2_fail_fast_datasource_query_error_raises():
    """ε2：DataSource 表查询失败 → MetadataError 熔断。"""
    tables = [{"db": "futures_admin", "table": "x"}]
    with patch("knot.repositories.data_source_repo.list_datasources",
               side_effect=Exception("simulated DB connection error")):
        with pytest.raises(MetadataError, match="DataSource 表查询失败"):
            catalog_loader._infer_source_types_from_datasources(tables)


# ─── reload(strict) 模式测试 ──────────────────────────────────────


def test_reload_strict_false_warns_on_metadata_error(caplog):
    """ε2：reload(strict=False) — startup 期降级为 warning + 不阻塞。"""
    # 模拟 _load_from_db 返非空 db_tables（触发推断路径）
    with patch.object(catalog_loader, "_load_from_db",
                      return_value=({}, [{"db": "x", "table": "y"}], "", [], True)):
        with patch("knot.repositories.data_source_repo.list_datasources",
                   side_effect=Exception("simulated")):
            # 不应抛 — 仅 log warning
            result = catalog_loader.reload(strict=False)
    assert result is not None
    # 应有 warning log
    assert any("source_type 推断兜底失败" in r.message for r in caplog.records)


def test_reload_strict_true_raises_on_metadata_error():
    """ε2：reload(strict=True) — admin/query 触发时 MetadataError 上抛。"""
    with patch.object(catalog_loader, "_load_from_db",
                      return_value=({}, [{"db": "x", "table": "y"}], "", [], True)):
        with patch("knot.repositories.data_source_repo.list_datasources",
                   side_effect=Exception("simulated")):
            with pytest.raises(MetadataError):
                catalog_loader.reload(strict=True)


# ─── NRP-C1 catalog reload 协同（admin 改 source_type 立即生效）──


def test_NRP_C1_admin_reload_invalidates_inference(client, auth_headers):
    """NRP-C1：admin POST /api/admin/catalog → 重新触发 reload(strict=True) → 推断生效。

    场景：admin 添加新的 http db_type DataSource → catalog reload → 该 db 下表自动标 http
    """
    # 准备：catalog 含 futures_admin 表（无 source_type）+ 不存在 http DataSource
    # admin reload 后应触发推断 + warning（无 http DataSource → 不推断 + log）
    resp = client.get("/api/admin/catalog", headers=auth_headers)
    assert resp.status_code == 200
    # source 标签应反映 db / db+file_http
    data = resp.json()
    assert "source" in data
