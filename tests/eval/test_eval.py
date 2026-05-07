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

from bi_agent.services import llm_client  # noqa: E402

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


def test_cases_loaded():
    """无 key 时也跑：保证 cases.yaml 至少被加载。"""
    assert len(CASES) >= 5, f"sample case 数 < 5，当前 {len(CASES)}"
    seen = set()
    for c in CASES:
        assert "id" in c and "question" in c, f"case 缺字段：{c}"
        assert c["id"] not in seen, f"重复 id：{c['id']}"
        seen.add(c["id"])
