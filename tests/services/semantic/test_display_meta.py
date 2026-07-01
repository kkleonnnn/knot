"""v0.7.23/.25 C1 — _semantic_display_meta 守护（呈现 meta：表头中文 #5 + 图表 dimension_cols 硬化 + 值格式 column_formats）。

- R-SL-169 column_labels = {metric.name → display}（缺 display → fallback name；不在 by_name → 跳过）
- R-SL-170 dimension_cols = lf.dimensions（**非 lf.metrics**）→ 前端 labelCols=dimension_cols /
  valueCols=结果列−dimension_cols = 全部度量（含 window/derived 列，∉ lf.metrics 但也 ∉ dimensions → 仍画，无回归）
- R-SL-181 column_formats = {metric.name → unit}（**仅非空 unit 入** → percentage 列 ×100+%；空/缺 → 不入 → 前端 fallback byte-equal）
"""
from types import SimpleNamespace

from knot.services.query_steps import _semantic_display_meta


def _lf(metrics, dimensions):
    # helper 仅访问 lf.metrics / lf.dimensions（pure）→ SimpleNamespace 即可
    return SimpleNamespace(metrics=metrics, dimensions=dimensions)


def test_column_labels_metric_display():
    labels, dim_cols, _ = _semantic_display_meta(
        _lf(["user_position_pnl"], ["market"]),
        {"user_position_pnl": {"name": "user_position_pnl", "display": "持仓盈亏"}},
    )
    assert labels == {"user_position_pnl": "持仓盈亏"}
    assert dim_cols == ["market"]


def test_empty_display_fallback_to_name():
    labels, _, _ = _semantic_display_meta(_lf(["gmv"], []), {"gmv": {"display": ""}})
    assert labels == {"gmv": "gmv"}  # 缺 display → fallback name（R-SL-169）


def test_metric_not_in_by_name_skipped():
    labels, _, _ = _semantic_display_meta(_lf(["gmv", "unknown"], []), {"gmv": {"display": "成交额"}})
    assert labels == {"gmv": "成交额"}  # unknown ∉ by_name → 跳过（前端 fallback raw）


def test_dimension_cols_is_lf_dimensions_not_metrics():
    # R-SL-170 承重：dimension_cols = lf.dimensions（非 lf.metrics）。窗口列（如 gmv_ma7）在 SQL
    # 输出但 ∉ lf → 也 ∉ dimension_cols → 前端 valueCols=cols−dimension_cols 含它 → 仍画（无回归）。
    _, dim_cols, _ = _semantic_display_meta(_lf(["gmv"], ["date"]), {"gmv": {"display": "GMV"}})
    assert dim_cols == ["date"]  # 仅维度；gmv / gmv_ma7 都不在 → 前端归 valueCol


def test_no_dimensions_empty_list():
    # 标量 metric（无维度）→ dimension_cols 空 → 前端 fallback typeof（单行 metric_card 不画图）
    _, dim_cols, _ = _semantic_display_meta(_lf(["gmv"], []), {"gmv": {"display": "GMV"}})
    assert dim_cols == []


def test_column_formats_only_nonempty_unit():
    # R-SL-181：仅非空 unit 入 column_formats；空/缺 unit metric 不入 → 前端 fmtValue else 分支 byte-equal
    _, _, formats = _semantic_display_meta(
        _lf(["future_fee_rate", "gmv"], []),
        {"future_fee_rate": {"display": "合约费率", "unit": "percentage"},
         "gmv": {"display": "成交额"}},  # gmv 无 unit key
    )
    assert formats == {"future_fee_rate": "percentage"}  # gmv（无 unit）不入


def test_column_formats_empty_unit_excluded():
    # unit="" 空串 → 不入（== 无 unit，前端默认渲染）
    _, _, formats = _semantic_display_meta(_lf(["gmv"], []), {"gmv": {"display": "GMV", "unit": ""}})
    assert formats == {}
