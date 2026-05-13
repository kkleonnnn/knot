"""tests/services/test_sql_planner_fan_out.py — v0.4.1.1 C 升级 runtime 守护单测。

测 sql_planner._is_fan_out 静态检测：
- ≥ 2 个 LEFT JOIN 到具名表 + 顶层 SELECT ≥ 2 个聚合 → True（fan-out 反模式）
- 单 LEFT JOIN / 单聚合 / 子查询 join / CTE → False（不误杀）
"""
from knot.services.agents.sql_planner import _is_fan_out


def test_fan_out_detects_two_left_joins_with_two_sums():
    sql = (
        "SELECT u.user_id, SUM(d.amt), SUM(t.amt) "
        "FROM users u "
        "LEFT JOIN deposits d ON u.id = d.user_id "
        "LEFT JOIN deals t ON u.id = t.user_id "
        "GROUP BY u.user_id"
    )
    is_fan, reason = _is_fan_out(sql)
    assert is_fan is True
    assert "聚合" in reason and "LEFT JOIN" in reason


def test_fan_out_detects_three_aggregates_three_joins():
    """user 报告的真实 SQL — reg + dep + deal（3 表 fan-out）。"""
    sql = (
        "SELECT reg.user_id, SUM(dep.deposit) AS total_deposit, "
        "       SUM(deal.future_match_amt) AS total_future_match_amt "
        "FROM demo_dwd.dwd_user_reg reg "
        "LEFT JOIN demo_dwd.dwd_user_deposit dep ON reg.user_id = dep.user_id "
        "LEFT JOIN demo_dwd.dwd_user_deal deal ON reg.user_id = deal.user_id "
        "GROUP BY reg.user_id "
        "HAVING SUM(dep.deposit) > 0 OR SUM(deal.future_match_amt) > 0"
    )
    is_fan, _ = _is_fan_out(sql)
    assert is_fan is True


def test_fan_out_skips_subquery_join_pre_aggregation():
    """正确写法 — 每个明细表先用子查询 GROUP BY 预聚合 → 不应误杀。"""
    sql = (
        "SELECT u.user_id, COALESCE(d.total, 0), COALESCE(t.total, 0) "
        "FROM users u "
        "LEFT JOIN (SELECT user_id, SUM(amt) AS total FROM deposits GROUP BY user_id) d "
        "       ON u.id = d.user_id "
        "LEFT JOIN (SELECT user_id, SUM(amt) AS total FROM deals    GROUP BY user_id) t "
        "       ON u.id = t.user_id"
    )
    is_fan, _ = _is_fan_out(sql)
    assert is_fan is False


def test_fan_out_skips_cte_pre_aggregation():
    """CTE 写法（顶层 WITH）→ 跳过守护。"""
    sql = (
        "WITH d AS (SELECT user_id, SUM(amt) AS total FROM deposits GROUP BY user_id), "
        "     t AS (SELECT user_id, SUM(amt) AS total FROM deals    GROUP BY user_id) "
        "SELECT u.user_id, d.total, t.total "
        "FROM users u "
        "LEFT JOIN d ON u.id = d.user_id "
        "LEFT JOIN t ON u.id = t.user_id"
    )
    is_fan, _ = _is_fan_out(sql)
    assert is_fan is False


def test_fan_out_skips_single_left_join():
    """单 LEFT JOIN 不会膨胀（只有一个明细表，没有跨表行数相乘）。"""
    sql = (
        "SELECT u.user_id, SUM(o.pay_amount) "
        "FROM users u LEFT JOIN orders o ON u.id = o.user_id "
        "GROUP BY u.user_id"
    )
    is_fan, _ = _is_fan_out(sql)
    assert is_fan is False


def test_fan_out_skips_single_aggregate():
    """单聚合（即使多 LEFT JOIN）不算 fan-out — 没膨胀方向。"""
    sql = (
        "SELECT u.user_id, MAX(o.pay_amount) "
        "FROM users u "
        "LEFT JOIN orders o ON u.id = o.user_id "
        "LEFT JOIN refunds r ON u.id = r.user_id "
        "GROUP BY u.user_id"
    )
    is_fan, _ = _is_fan_out(sql)
    assert is_fan is False


def test_fan_out_handles_empty_or_invalid_sql():
    assert _is_fan_out("") == (False, "")
    assert _is_fan_out("not a select") == (False, "")
