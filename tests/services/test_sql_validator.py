"""tests/services/test_sql_validator.py — v0.5.1 SQL AST 笛卡尔积守护单测。

D-2 测试骨架优先（Stage 3 守护者末段指示）：CTE 递归 (R-83) + C4 恒真 ON 优先。
其余 C1/C2/C3 + R-89/R-80/R-93 后续覆盖。
"""
from unittest.mock import patch

import pytest

from knot.services.sql_validator import is_cartesian


# ── D-2 优先组：R-83 CTE/子查询递归 ──────────────────────────────────────
def test_R83_cte_inner_comma_join_caught():
    """CTE 内的旧式逗号 join → 必须 catch。"""
    sql = "WITH x AS (SELECT * FROM a, b) SELECT * FROM x"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "comma-join" in reason or "tables" in reason


def test_R83_subquery_inner_cross_join_caught():
    """子查询内的 CROSS JOIN → 必须 catch（外层是合法的）。"""
    sql = "SELECT * FROM (SELECT * FROM a CROSS JOIN b) t"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "Cartesian product" in reason


def test_R83_subquery_inner_missing_on_caught():
    """子查询内缺 ON。"""
    sql = "SELECT u.id FROM users u WHERE u.id IN (SELECT a.id FROM a JOIN b)"
    is_c, _ = is_cartesian(sql)
    assert is_c is True


# ── D-2 优先组：C4 恒真 ON ─────────────────────────────────────────────
def test_C4_tautological_one_equals_one():
    """ON 1=1 经典恒真。"""
    sql = "SELECT * FROM users u JOIN orders o ON 1=1"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "Tautological" in reason
    assert "1 = 1" in reason or "1=1" in reason


def test_C4_tautological_boolean_true():
    """ON TRUE。"""
    sql = "SELECT * FROM a JOIN b ON TRUE"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "Tautological" in reason


def test_C4_tautological_string_literal_eq():
    """ON 'x'='x' — 字符串字面量恒真。"""
    sql = "SELECT * FROM a JOIN b ON 'x'='x'"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "Tautological" in reason


def test_C4_legitimate_eq_not_tautological():
    """ON a.id=b.id — 列引用合法等值，绝不能误杀。"""
    sql = "SELECT * FROM a JOIN b ON a.id=b.id"
    is_c, _ = is_cartesian(sql)
    assert is_c is False


# ── C1 旧式逗号 ─────────────────────────────────────────────────────
def test_C1_comma_with_where_relation():
    """`FROM a, b WHERE a.id=b.id` — 即使 WHERE 补关联条件也拒（D4 锁定）。"""
    sql = "SELECT * FROM a, b WHERE a.id=b.id"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "comma-join" in reason


def test_C1_three_tables_comma():
    """`FROM a, b, c` — 多表逗号。"""
    sql = "SELECT * FROM a, b, c"
    is_c, _ = is_cartesian(sql)
    assert is_c is True


# ── C2 CROSS JOIN ─────────────────────────────────────────────────────
def test_C2_explicit_cross_join():
    sql = "SELECT * FROM a CROSS JOIN b"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "CROSS JOIN" in reason


# ── C3 缺 ON ───────────────────────────────────────────────────────
def test_C3_inner_join_missing_on():
    sql = "SELECT * FROM a JOIN b"
    is_c, reason = is_cartesian(sql)
    assert is_c is True
    assert "without ON" in reason


def test_C3_left_join_missing_on():
    sql = "SELECT * FROM a LEFT JOIN b"
    is_c, _ = is_cartesian(sql)
    assert is_c is True


def test_C3_using_clause_legitimate():
    """USING(id) 是合法 join 条件，不能误杀。"""
    sql = "SELECT * FROM a JOIN b USING(id)"
    is_c, _ = is_cartesian(sql)
    assert is_c is False


# ── 正例 — 不能误杀 ────────────────────────────────────────────────
def test_normal_single_table():
    is_c, _ = is_cartesian("SELECT id FROM users")
    assert is_c is False


def test_normal_inner_join_with_on():
    sql = "SELECT u.id FROM users u JOIN orders o ON u.id = o.user_id"
    is_c, _ = is_cartesian(sql)
    assert is_c is False


def test_normal_three_table_chain_join():
    sql = (
        "SELECT u.id FROM users u "
        "JOIN orders o ON u.id = o.user_id "
        "LEFT JOIN refunds r ON o.id = r.order_id"
    )
    is_c, _ = is_cartesian(sql)
    assert is_c is False


# ── R-89 输入预检 ────────────────────────────────────────────────────
def test_R89_oversized_sql_fail_open():
    """超长 SQL → fail-open（不拒收）。"""
    sql = "SELECT * FROM a JOIN b ON a.id=b.id WHERE x = " + "1 OR x = ".join(["?"] * 10001)
    assert len(sql) > 100_000
    is_c, _ = is_cartesian(sql)
    assert is_c is False  # fail-open


def test_R89_deep_paren_nesting_fail_open():
    """超深括号嵌套 → fail-open。"""
    sql = "SELECT * FROM users WHERE id = " + "(" * 150 + "1" + ")" * 150
    is_c, _ = is_cartesian(sql)
    assert is_c is False  # fail-open


# ── R-80 sqlglot 缺包 / 解析失败 fail-open ──────────────────────────
def test_R80_sqlglot_import_failure_fail_open():
    """sqlglot import 失败 → fail-open（不阻断 SQL，业务降级），但 C1 文本侧
    仍生效（comma 不依赖 sqlglot）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "sqlglot" or name.startswith("sqlglot."):
            raise ImportError("simulated sqlglot missing")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        # 非 C1 case，sqlglot 失败应 fail-open（C2/C3/C4 不再触发）
        is_c, _ = is_cartesian("SELECT * FROM a CROSS JOIN b")
        assert is_c is False


def test_R80_parse_failure_fail_open():
    """SQL 解析失败 → fail-open（C1 已通过，无逗号触发）。"""
    sql = "SELECT FROM JOIN ON garbage @ # &"  # 无逗号 → 不触发 C1，进 sqlglot
    is_c, _ = is_cartesian(sql)
    assert is_c is False


# ── R-93 v0.4.5 加密列兼容 ───────────────────────────────────────────
def test_R93_enc_v1_prefix_in_where_not_misjudged():
    """WHERE 含 `enc_v1:` 加密字段值的合法 SQL — 必须不误判。"""
    sql = (
        "SELECT id, name FROM users u "
        "JOIN api_keys k ON u.id = k.user_id "
        "WHERE k.value = 'enc_v1:Z0FBQUFBQm5lZW5lUTBKVw=='"
    )
    is_c, reason = is_cartesian(sql)
    assert is_c is False, f"R-93 failed: {reason}"


# ── 边界 ────────────────────────────────────────────────────────────
def test_empty_or_whitespace():
    assert is_cartesian("") == (False, "")
    assert is_cartesian("   \n\t  ") == (False, "")


def test_None_safe():
    """None 输入也 fail-open，不抛。"""
    is_c, _ = is_cartesian(None)  # type: ignore[arg-type]
    assert is_c is False
