"""tests/adapters/test_doris_limit_guard.py — auto-LIMIT AST 守护（v0.8.0 B6.1 §1.9）。

旧 substring `"LIMIT" in sql.upper()` 被 filter 片段内 LIMIT token 绕过 → 全量返回。
`_has_top_level_limit` 用 sqlglot AST 判顶层 LIMIT（POC union/CTE/subquery/plain 全对）。
"""
from __future__ import annotations

import pytest

from knot.adapters.db.doris import _has_top_level_limit


@pytest.mark.parametrize("sql", [
    "SELECT a FROM t LIMIT 5",                                   # plain 顶层 LIMIT
    "SELECT a FROM t UNION SELECT a FROM u LIMIT 5",             # union 根 LIMIT（挂 Union.args）
    "WITH r AS (SELECT a FROM t) SELECT a FROM r LIMIT 5",       # CTE 外层 LIMIT
])
def test_top_level_limit_detected(sql):
    assert _has_top_level_limit(sql) is True


@pytest.mark.parametrize("sql", [
    "SELECT a FROM t",                                           # 无 LIMIT
    "SELECT a FROM t WHERE note = 'has LIMIT here'",             # 字符串字面含 LIMIT token（旧 substring 被绕）
    "SELECT a FROM t WHERE id IN (SELECT id FROM u LIMIT 10)",   # 内层子查询 LIMIT（非顶层）
    "WITH r AS (SELECT a FROM t LIMIT 3) SELECT a FROM r",       # CTE body LIMIT（非顶层）
])
def test_no_top_level_limit(sql):
    # 这些都须补外层 LIMIT（旧 substring 判断会误以为已有 LIMIT → 全量返回）
    assert _has_top_level_limit(sql) is False
