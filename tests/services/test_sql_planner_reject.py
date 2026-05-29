"""v0.6.2.1 commit 3 — F3 C3 sql_planner 非 SELECT 起手拒识守护测试

覆盖 R-PB-C3-1 + R-PB-C3-2 + Stage 2 Q3 边界 case：
  - SELECT / WITH 正向 case（含 markdown / 多种 case 形态）
  - 中文非 SQL 输出（生产 e38de5e76703 类）→ 必拒识
  - 注释 / 块注释 / 空白 / 纯空 → 拒识
  - 边界：EXPLAIN / DESC / UNION 起手 → 拒识（仅 SELECT/WITH 接受）
"""
from knot.services.agents.sql_planner_tools import (
    _VALID_SQL_OPENERS,
    _get_first_sql_keyword,
    _strip_sql,
)

# ─── 正向 — SELECT / WITH 起手 ─────────────────────────────────────


def test_select_simple():
    assert _get_first_sql_keyword("SELECT * FROM t") == "SELECT"


def test_select_lowercase():
    assert _get_first_sql_keyword("select id from t") == "SELECT"


def test_with_cte():
    assert _get_first_sql_keyword("WITH cte AS (SELECT * FROM t) SELECT * FROM cte") == "WITH"


def test_with_cte_lowercase():
    assert _get_first_sql_keyword("with cte as (select 1) select * from cte") == "WITH"


def test_markdown_sql_block():
    """LLM 输出常含 markdown ```sql ... ``` 包装；_strip_sql 已剥。"""
    assert _get_first_sql_keyword("```sql\nSELECT 1\n```") == "SELECT"


def test_markdown_plain_block():
    """无语言标识 markdown ``` ... ``` 也应剥。"""
    assert _get_first_sql_keyword("```\nWITH cte AS (SELECT 1) SELECT * FROM cte\n```") == "WITH"


def test_leading_whitespace():
    assert _get_first_sql_keyword("   \n\t  SELECT 1") == "SELECT"


def test_line_comment_before_select():
    """-- 行注释起手 → 跳过 → 真正首关键字 SELECT 检测到。"""
    assert _get_first_sql_keyword("-- query for active users\nSELECT id FROM users") == "SELECT"


def test_block_comment_before_with():
    """/* 块注释 */ 起手 → 跳 → WITH 检测到。"""
    assert _get_first_sql_keyword("/* this is a CTE */\nWITH cte AS (SELECT 1) SELECT * FROM cte") == "WITH"


def test_multiple_comments_before_select():
    assert _get_first_sql_keyword("-- comment 1\n-- comment 2\n/* block */\nSELECT 1") == "SELECT"


# ─── 反向 — 生产 e38de5e76703 类 LLM 中文非 SQL 输出 ─────────────


def test_chinese_no_sql_text():
    """生产 bug：LLM 输出'无法直接 SQL 查询 HTTP 虚拟表' → 必非 SELECT/WITH。"""
    result = _get_first_sql_keyword("无法直接 SQL 查询 HTTP 虚拟表。查询用户当前持仓挂单情况需要通过其他方式获取数据，请联系相关人员。")
    assert result == "" or result not in _VALID_SQL_OPENERS


def test_chinese_apologetic():
    result = _get_first_sql_keyword("抱歉，本问题需要外部 API，不适用 SQL 查询")
    assert result not in _VALID_SQL_OPENERS


# ─── 反向 — 其他非合法起手关键字 ─────────────────────────────────


def test_explain_not_accepted():
    """EXPLAIN 不在 SELECT/WITH 白名单（虽然技术上是 SQL）。"""
    assert _get_first_sql_keyword("EXPLAIN SELECT * FROM t") not in _VALID_SQL_OPENERS


def test_describe_not_accepted():
    assert _get_first_sql_keyword("DESC table_name") not in _VALID_SQL_OPENERS


def test_insert_not_accepted():
    """KNOT 仅做 SELECT/WITH 查询；INSERT/UPDATE/DELETE 严禁出现。"""
    assert _get_first_sql_keyword("INSERT INTO t VALUES (1)") not in _VALID_SQL_OPENERS


def test_union_not_accepted():
    """UNION 不应单独起手（必在 SELECT 之后）— 守护边界。"""
    assert _get_first_sql_keyword("UNION SELECT 1") not in _VALID_SQL_OPENERS


# ─── 反向 — 退化输入 ─────────────────────────────────────────────


def test_empty_string():
    assert _get_first_sql_keyword("") == ""


def test_only_whitespace():
    assert _get_first_sql_keyword("   \n\t  ") == ""


def test_only_comments():
    assert _get_first_sql_keyword("-- just a comment\n/* nothing else */") == ""


def test_only_markdown_fence():
    assert _get_first_sql_keyword("```sql\n```") == ""


def test_numeric_only():
    """纯数字开头（非合法 SQL token start）。"""
    assert _get_first_sql_keyword("123 SELECT FROM t") not in _VALID_SQL_OPENERS


# ─── _strip_sql 既有行为 sustained（防回归）────────────────────


def test_strip_sql_sustained():
    """_strip_sql 既有行为 byte-equal：markdown 剥 + 反引号剥。"""
    assert _strip_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert _strip_sql("`SELECT 1`") == "SELECT 1"
    assert _strip_sql("  SELECT 1  ") == "SELECT 1"
