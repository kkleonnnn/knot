"""v0.6.2.2 commit 3 — F4 复合 metric 守护测试

覆盖 R-PB-A5-1（单值 byte-equal）+ R-PB-A5-2（prompt 指引 + runtime AST 双层守护）+ NRP-A5-1（多值网格 fallback）+ NRP-A5-2（fan-out runtime 守护澄清）。

KNOT 前端无 JS test runner（仅 eslint + build）→ MetricCard 渲染用 Python 静态源断言守护
（v0.6.0.9 hardening 模式）；NRP-A5-2 复用既有 v0.5.1 sql_validator fan-out runtime 守护。
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_METRIC_CARD = _REPO / "frontend/src/screens/chat/ResultBlock/MetricCard.jsx"
_CLARIFIER = _REPO / "knot/prompts/clarifier.md"
_SQL_PLANNER = _REPO / "knot/prompts/sql_planner.md"


# ─── F1 — MetricCard 多值网格 dispatch（静态源断言）────────────────


def test_F1_metric_card_multi_value_dispatch():
    """numericCols.length > 1 → _MultiStatGrid 分流（复合 metric 不再丢弃第 2+ 指标）。"""
    src = _METRIC_CARD.read_text(encoding="utf-8")
    assert "numericCols.length > 1" in src, "MetricCard 必含多值分流判定"
    assert "_MultiStatGrid" in src, "MetricCard 必含多值网格子组件"


def test_NRP_A5_1_multi_grid_auto_fit():
    """NRP-A5-1：多值网格 auto-fit minmax 自适应 — 列数过多自然换行（>6 列不拥挤）。"""
    src = _METRIC_CARD.read_text(encoding="utf-8")
    assert "auto-fit" in src and "minmax(160px" in src, \
        "多值网格必用 repeat(auto-fit, minmax(160px,1fr)) 自适应（NRP-A5-1 >6 列 fallback）"


def test_R_PB_A5_1_single_value_branch_preserved():
    """R-PB-A5-1：单值路径渲染结构 byte-equal — 48px 大数字卡片 + valueCol/labelCol 保留。"""
    src = _METRIC_CARD.read_text(encoding="utf-8")
    assert "_SingleMetric" in src, "单值分支必抽 _SingleMetric"
    # 单值大数字卡片关键字面（与 v0.6.0.2 抽出版 byte-equal）
    assert "fontSize: 48" in src, "单值大数字 48px 必保留"
    assert "numericCols[0] || cols[0]" in src, "单值 valueCol 取首数值列逻辑必保留"


# ─── F2 — clarifier 复合 metric 识别段 ────────────────────────────


def test_F2_clarifier_composite_metric_section():
    """clarifier.md §8 复合 metric 识别段 — 一句问 2+ 聚合 → intent=metric + 保留全部指标。"""
    src = _CLARIFIER.read_text(encoding="utf-8")
    assert "复合 metric" in src, "clarifier.md 必含复合 metric 段"
    assert "保留全部指标" in src, "复合 metric 必明示 refined 保留全部指标（不丢第 2+）"
    # 生产 bug 示例落地
    assert "今日合约交易量和充值" in src, "必含生产 bug 示例（Task #17）"


# ─── F3 — sql_planner 复合 metric 中文别名/CTE 指引 ──────────────


def test_F3_sql_planner_composite_metric_section():
    """sql_planner.md 复合 metric 段 — 同表单 SELECT 多聚合 / 跨表 CTE 预聚合 + 中文别名。"""
    src = _SQL_PLANNER.read_text(encoding="utf-8")
    assert "复合 metric" in src, "sql_planner.md 必含复合 metric 段"
    assert "中文别名" in src, "必明示中文别名（前端多值卡片 label）"
    assert "AS 交易量" in src, "必含中文别名示例"
    assert "CTE" in src, "跨表必 CTE 预聚合（复用 fan-out 防御）"


# ─── R-PB-A5-2 / NRP-A5-2 — fan-out runtime 硬守护澄清（复用 v0.5.1 AST）──


def test_NRP_A5_2_composite_cross_table_fanout_runtime_guard():
    """NRP-A5-2：复合 metric 跨表若 LLM 误写直接 JOIN（非 CTE 预聚合）→ 既有 v0.5.1 AST 守护拦截。

    R-PB-A5-2 守护粒度澄清：prompt 指引 = 软约束（commit 2 F3）；
    runtime fan-out 硬守护 sustained 既有 _is_fan_out（不重造）。
    本测试验证复合 metric 跨表错误写法仍被既有守护拦截。
    """
    from knot.services.agents.sql_planner import _is_fan_out

    # 复合 metric 跨表错误写法（交易量 + 充值，直接 2 LEFT JOIN 到明细表 → fan-out）
    bad_sql = (
        "SELECT u.user_id, SUM(deal.volume) AS 交易量, SUM(dep.amount) AS 充值额 "
        "FROM users u "
        "LEFT JOIN deals deal ON u.id = deal.user_id "
        "LEFT JOIN deposits dep ON u.id = dep.user_id "
        "GROUP BY u.user_id"
    )
    is_fan, _ = _is_fan_out(bad_sql)
    assert is_fan is True, "复合 metric 跨表直接 JOIN（非 CTE 预聚合）必被既有 fan-out 守护拦截"


def test_NRP_A5_2_composite_cte_preaggregation_not_rejected():
    """复合 metric 跨表正确写法（CTE 预聚合，F3 指引）→ 不被 fan-out 守护误杀。"""
    from knot.services.agents.sql_planner import _is_fan_out

    good_sql = (
        "WITH t AS (SELECT SUM(volume) AS v FROM deals WHERE dt='2026-06-06'), "
        "     d AS (SELECT SUM(amount) AS a FROM deposits WHERE dt='2026-06-06') "
        "SELECT t.v AS 交易量, d.a AS 充值额 FROM t, d"
    )
    is_fan, _ = _is_fan_out(good_sql)
    assert is_fan is False, "CTE 预聚合复合 metric（F3 正确写法）不应被误杀"


# ─── 同表复合 metric — 纯前端 bug 路径（commit 1 调查主因）────────


def test_same_table_composite_metric_not_fanout():
    """同表复合 metric（SELECT SUM(a), SUM(b) FROM 同表）→ 非 fan-out，纯前端展示问题。

    commit 1 根因调查：同表复合 metric SQL 正确，bug 完全在前端 MetricCard numericCols[0]。
    """
    from knot.services.agents.sql_planner import _is_fan_out

    same_table_sql = (
        "SELECT SUM(volume) AS 交易量, SUM(deposit_amount) AS 充值额 "
        "FROM ohx_dwd.dwd_trade_summary WHERE dt='2026-06-06'"
    )
    is_fan, _ = _is_fan_out(same_table_sql)
    assert is_fan is False, "同表复合 metric 非 fan-out（commit 1 调查：纯前端 bug）"
    # 验证多列数值 — 前端 numericCols 会算出 2 列 → MetricCard 多值网格触发
    assert len(re.findall(r"\bSUM\(", same_table_sql)) == 2, "同表 2 聚合列 → 触发多值网格"
