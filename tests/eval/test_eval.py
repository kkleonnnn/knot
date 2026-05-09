"""tests/eval/test_eval.py — 把 cases.yaml 喂给 llm_client.generate_sql，做静态断言。

运行：
    OPENROUTER_API_KEY=sk-or-... pytest tests/eval -v

无 key 时整组 skip，避免 CI 误炸 / 烧 token。

v0.4.1.1：加 _check_no_cartesian_join 笛卡尔积守护正则（R-S2 加强）：
- 多表 SQL（matched_tables ≥ 2）必须有 \\bjoin\\b + \\bon\\b
- 严禁 `FROM a, b` 旧式逗号 join 句式（潜在笛卡尔积高危）
"""
import os
import re

import pytest

from tests.eval.conftest import load_cases  # noqa: E402

from knot.services import llm_client  # noqa: E402

_REQUIRES_KEY = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="需要 OPENROUTER_API_KEY 才能跑 LLM eval",
)

CASES = load_cases()


# v0.4.1.1: 旧式 FROM a, b 逗号 join 检测正则
# 匹配 FROM <id>(.<id>)? <可选alias> , <id> — 带可选 db 前缀 + 可选表别名（with/without AS）
_COMMA_FROM_RE = re.compile(
    r"\bfrom\s+\w+(?:\.\w+)?(?:\s+(?:as\s+)?\w+)?\s*,\s*\w+",
    re.IGNORECASE,
)


def _check_no_cartesian_join(case_id: str, sql: str, must_tables: list):
    """涉及 ≥ 2 个 must_tables 的 SQL 必须有 JOIN + ON，且禁旧式 `FROM a, b`。"""
    sql_lower = sql.lower()
    matched = [t for t in must_tables if t.lower() in sql_lower]
    if len(matched) < 2:
        return
    assert re.search(r"\bjoin\b", sql_lower), (
        f"[{case_id}] 多表 SQL 缺 JOIN（涉及 {matched}）: {sql}"
    )
    assert re.search(r"\bon\b", sql_lower), (
        f"[{case_id}] 多表 SQL 缺 ON 关联条件（涉及 {matched}）: {sql}"
    )
    assert not _COMMA_FROM_RE.search(sql_lower), (
        f"[{case_id}] 检测到 `FROM a, b` 旧式 join 句式（潜在笛卡尔积，涉及 {matched}）: {sql}"
    )


def _check_fan_out_uses_subquery_aggregation(case_id: str, sql: str, tags: list):
    """v0.4.1.1 实战补丁：tag=fan_out 的 case 必须用子查询/CTE 预聚合再 JOIN。

    判定：SQL 必须含 ≥ 2 个 `group by`（外层 + 子查询；或两个独立子查询；或 CTE 多个）。
    bad 模式 SUM(d.amt), SUM(o.amt) FROM u LEFT JOIN deposits d LEFT JOIN orders o GROUP BY u.id
    仅 1 个 GROUP BY → 必失败。
    good 模式 LEFT JOIN (SELECT ... GROUP BY uid) d LEFT JOIN (SELECT ... GROUP BY uid) o
    含 2 个 GROUP BY（两个子查询）→ pass。
    """
    if "fan_out" not in (tags or []):
        return
    sql_lower = sql.lower()
    n_group_by = len(re.findall(r"\bgroup\s+by\b", sql_lower))
    assert n_group_by >= 2, (
        f"[{case_id}] Fan-out 防御：tag=fan_out 的 case 必须用子查询/CTE 预聚合再 JOIN。"
        f"SQL 仅含 {n_group_by} 个 GROUP BY，预期 ≥ 2（外层多 SUM + 单层 GROUP BY 是膨胀反模式）: {sql}"
    )


# ── v0.4.2 SQL 复杂度横切（资深 Stage 2 AST hybrid 决议）─────────────────────


def _ast_parse_optional(sql: str):
    """尝试 sqlglot AST 解析；失败返 None（fallback 走纯正则）。"""
    try:
        import sqlglot
        return sqlglot.parse_one(sql, dialect="mysql")
    except Exception:
        return None


def _check_subquery_present(case_id: str, sql: str):
    """tag=subquery：SQL 嵌套 SELECT ≥ 2 次（外层 + ≥1 子查询/EXISTS/标量）。"""
    ast = _ast_parse_optional(sql)
    if ast is not None:
        try:
            from sqlglot import exp
            selects = list(ast.find_all(exp.Select))
            if len(selects) >= 2:
                return
        except Exception:
            pass
    n = len(re.findall(r"\bselect\b", sql.lower()))
    assert n >= 2, f"[{case_id}] subquery case 至少含 2 个 SELECT: {sql}"


def _check_window_with_partition_or_order(case_id: str, sql: str):
    """tag=window：SQL 必须 OVER (...)，且 OVER 内必须 PARTITION BY 或 ORDER BY。"""
    ast = _ast_parse_optional(sql)
    if ast is not None:
        try:
            from sqlglot import exp
            windows = list(ast.find_all(exp.Window))
            if windows:
                for w in windows:
                    if not (w.args.get("partition_by") or w.args.get("order")):
                        raise AssertionError(
                            f"[{case_id}] window 缺 PARTITION BY 或 ORDER BY: {sql}"
                        )
                return
        except AssertionError:
            raise
        except Exception:
            pass
    sql_lower = sql.lower()
    assert re.search(r"\bover\s*\(", sql_lower), f"[{case_id}] window case 缺 OVER (...): {sql}"
    assert re.search(r"\b(?:partition\s+by|order\s+by)\b", sql_lower), (
        f"[{case_id}] window 缺 PARTITION BY 或 ORDER BY（OVER() 无内容是非法窗口）: {sql}"
    )


def _check_cte_uses_with(case_id: str, sql: str):
    """tag=cte：SQL 必须以 WITH 起手 + AST 找到 CTE expression。"""
    sql_no_comments = re.sub(
        r"--.*?$|/\*.*?\*/", "", sql.strip().lower(),
        flags=re.MULTILINE | re.DOTALL,
    ).strip()
    assert sql_no_comments.startswith("with "), f"[{case_id}] CTE case 必须以 WITH 起手: {sql}"
    ast = _ast_parse_optional(sql)
    if ast is not None:
        try:
            from sqlglot import exp
            ctes = list(ast.find_all(exp.CTE))
            assert len(ctes) >= 1, f"[{case_id}] AST 解析无 CTE expression: {sql}"
        except AssertionError:
            raise
        except Exception:
            pass


def _check_complexity(case_id: str, sql: str, tags: list):
    """v0.4.2 dispatcher（资深 AST hybrid 决议）：按 tag 调对应守护检查。"""
    tags = tags or []
    if "subquery" in tags:
        _check_subquery_present(case_id, sql)
    if "window" in tags:
        _check_window_with_partition_or_order(case_id, sql)
    if "cte" in tags:
        _check_cte_uses_with(case_id, sql)


@_REQUIRES_KEY
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case, fake_schema):
    expects = case.get("expects", {})
    result = llm_client.generate_sql(
        question=case["question"],
        schema_text=fake_schema,
        model_key=os.getenv("EVAL_MODEL", "google/gemini-2.0-flash-001"),
        api_key="",
        business_context="",
        history=[],
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    sql = (result.get("sql") or "").lower()
    assert sql, f"[{case['id']}] LLM 没产出 SQL: {result.get('error')}"

    must_tables = expects.get("must_tables", [])
    for tbl in must_tables:
        assert tbl.lower() in sql, f"[{case['id']}] SQL 没用到表 {tbl}：{sql}"

    for kw in expects.get("must_keywords", []):
        assert kw.lower() in sql, f"[{case['id']}] SQL 缺关键词 {kw!r}：{sql}"

    for kw in expects.get("forbid_keywords", []):
        assert kw.lower() not in sql, f"[{case['id']}] SQL 命中禁止词 {kw!r}：{sql}"

    # v0.4.1.1 笛卡尔积守护：多表 SQL 必须 JOIN + ON 且禁旧式 FROM a,b
    _check_no_cartesian_join(case["id"], sql, must_tables)
    # v0.4.1.1 实战补丁：tag=fan_out 的 case 必须用子查询/CTE 预聚合
    _check_fan_out_uses_subquery_aggregation(case["id"], sql, case.get("tags", []))
    # v0.4.2 SQL 复杂度横切（资深 AST hybrid 决议）：subquery/window/cte 守护
    _check_complexity(case["id"], sql, case.get("tags", []))


# ── 守护正则纯单元测试（无 LLM key 也跑） ───────────────────────────────────


def test_check_no_cartesian_join_single_table_passes():
    """单表 SQL 不应被误杀。"""
    _check_no_cartesian_join("smoke", "select count(*) from users", ["users", "orders"])


def test_check_no_cartesian_join_proper_join_passes():
    sql = "select u.user_id, sum(o.pay_amount) from users u join orders o on u.user_id = o.user_id group by u.user_id"
    _check_no_cartesian_join("smoke", sql, ["users", "orders"])


def test_check_no_cartesian_join_left_join_passes():
    sql = "select u.user_id from users u left join orders o on u.user_id = o.user_id where o.user_id is null"
    _check_no_cartesian_join("smoke", sql, ["users", "orders"])


def test_check_no_cartesian_join_missing_join_fails():
    sql = "select u.user_id, o.pay_amount from users u, orders o where u.user_id = o.user_id"
    with pytest.raises(AssertionError, match="JOIN"):
        _check_no_cartesian_join("smoke", sql, ["users", "orders"])


def test_check_no_cartesian_join_comma_from_fails_even_with_join():
    """SQL 已有 JOIN + ON，但仍混了 `FROM a, b` 旧式句式 → fail（潜在笛卡尔积高危）。"""
    # users 主表 + comma-FROM 引入 logs 高危句式 + 与 orders 用 join + on（看起来"合规"）
    sql = (
        "select u.user_id from users u, logs l "
        "join orders o on u.user_id = o.user_id "
        "where u.user_id = l.user_id"
    )
    with pytest.raises(AssertionError, match="FROM"):
        _check_no_cartesian_join("smoke", sql, ["users", "orders"])


def test_check_no_cartesian_join_missing_on_fails():
    """JOIN 没 ON 子句 → fail（这是真正的 cross join）。"""
    sql = "select * from users u cross join orders o"
    with pytest.raises(AssertionError, match="ON"):
        _check_no_cartesian_join("smoke", sql, ["users", "orders"])


# ── Fan-out 守护单测（无 LLM key 也跑） ─────────────────────────────────


def test_fan_out_check_skips_when_tag_absent():
    """非 fan_out tag 的 case 不应被检测（向下兼容）。"""
    bad_sql = "select u.id, sum(d.amt), sum(o.amt) from u left join d on u.id=d.uid left join o on u.id=o.uid group by u.id"
    _check_fan_out_uses_subquery_aggregation("smoke", bad_sql, [])  # 应不抛
    _check_fan_out_uses_subquery_aggregation("smoke", bad_sql, ["multi_table"])  # 应不抛


def test_fan_out_check_fails_on_single_group_by_with_multi_left_joins():
    """fan-out 反模式：外层多个 SUM + 单层 GROUP BY → fail。"""
    bad_sql = (
        "select u.user_id, sum(d.amt), sum(o.amt) from users u "
        "left join deposits d on u.id = d.user_id "
        "left join orders   o on u.id = o.user_id "
        "group by u.user_id"
    )
    with pytest.raises(AssertionError, match="Fan-out"):
        _check_fan_out_uses_subquery_aggregation("smoke", bad_sql, ["fan_out"])


def test_fan_out_check_passes_with_subquery_pre_aggregation():
    """正确写法：每个明细表先按 grain 预聚合（≥ 2 个 group by） → pass。"""
    good_sql = (
        "select u.user_id, d.total, o.total from users u "
        "left join (select user_id, sum(amt) as total from deposits group by user_id) d "
        "       on u.id = d.user_id "
        "left join (select user_id, sum(amt) as total from orders   group by user_id) o "
        "       on u.id = o.user_id"
    )
    # 不应抛
    _check_fan_out_uses_subquery_aggregation("smoke", good_sql, ["fan_out"])


def test_fan_out_check_passes_with_cte_pre_aggregation():
    """CTE 写法（≥ 2 个 group by）也应 pass。"""
    good_sql = (
        "with d as (select user_id, sum(amt) as total from deposits group by user_id), "
        "     o as (select user_id, sum(amt) as total from orders   group by user_id) "
        "select u.user_id, d.total, o.total from users u "
        "left join d on u.id = d.user_id "
        "left join o on u.id = o.user_id"
    )
    _check_fan_out_uses_subquery_aggregation("smoke", good_sql, ["fan_out"])


def test_cases_loaded():
    """无 key 时也跑：保证 cases.yaml 至少被加载。"""
    assert len(CASES) >= 5, f"sample case 数 < 5，当前 {len(CASES)}"
    seen = set()
    for c in CASES:
        assert "id" in c and "question" in c, f"case 缺字段：{c}"
        assert c["id"] not in seen, f"重复 id：{c['id']}"
        seen.add(c["id"])


def test_eval_cases_total_at_least_110():
    """v0.4.2 eval 复杂度横切扩量：cases ≥ 110。"""
    assert len(CASES) >= 110, f"v0.4.2 cases 应 ≥ 110，当前 {len(CASES)}"


def test_eval_cases_complexity_tag_coverage():
    """v0.4.2 R-S6 教训：每个复杂度维度必须 ≥ 6 case，混合 ≥ 3。"""
    counts = {"subquery": 0, "window": 0, "cte": 0, "mixed": 0}
    for c in CASES:
        for tag in c.get("tags", []) or []:
            if tag in counts:
                counts[tag] += 1
    assert counts["subquery"] >= 6, f"subquery cases 不足 6: {counts['subquery']}"
    assert counts["window"]   >= 6, f"window cases 不足 6: {counts['window']}"
    assert counts["cte"]      >= 6, f"cte cases 不足 6: {counts['cte']}"
    assert counts["mixed"]    >= 3, f"mixed cases 不足 3: {counts['mixed']}"


# ── 复杂度 dispatcher 守护单测（无 LLM key 也跑） ───────────────────────────


def test_complexity_subquery_passes_with_two_selects():
    sql = "select user_id from users where id in (select user_id from orders)"
    _check_complexity("smoke", sql, ["subquery"])


def test_complexity_subquery_fails_on_single_select():
    sql = "select user_id from users"
    with pytest.raises(AssertionError, match="subquery|SELECT"):
        _check_complexity("smoke", sql, ["subquery"])


def test_complexity_window_passes_with_partition_by():
    sql = "select user_id, row_number() over (partition by user_id order by created_at desc) rn from orders"
    _check_complexity("smoke", sql, ["window"])


def test_complexity_window_fails_when_over_empty():
    """OVER () 无 partition / order — 守护应 raise。"""
    sql = "select avg(pay_amount) over () from orders"
    with pytest.raises(AssertionError, match="PARTITION|ORDER"):
        _check_complexity("smoke", sql, ["window"])


def test_complexity_cte_passes_with_with_clause():
    sql = "with t as (select user_id, sum(amt) total from orders group by user_id) select * from t"
    _check_complexity("smoke", sql, ["cte"])


def test_complexity_cte_fails_when_no_with_at_top():
    sql = "select user_id, sum(amt) from orders group by user_id"
    with pytest.raises(AssertionError, match="WITH"):
        _check_complexity("smoke", sql, ["cte"])


def test_complexity_dispatcher_skips_when_no_relevant_tags():
    """非 subquery/window/cte tag 的 case 一律跳过守护（向下兼容）。"""
    sql = "select 1"
    _check_complexity("smoke", sql, [])
    _check_complexity("smoke", sql, ["multi_table"])
    _check_complexity("smoke", sql, ["edge_case"])
