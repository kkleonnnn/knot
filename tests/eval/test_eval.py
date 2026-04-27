"""tests/eval/test_eval.py — 把 cases.yaml 喂给 llm_client.generate_sql，做静态断言。

运行：
    OPENROUTER_API_KEY=sk-or-... pytest tests/eval -v

无 key 时整组 skip，避免 CI 误炸 / 烧 token。
"""
import os

import pytest

from conftest import load_cases  # noqa: E402  (sys.path 在 conftest 中已设置)

import llm_client  # noqa: E402

_REQUIRES_KEY = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="需要 OPENROUTER_API_KEY 才能跑 LLM eval",
)

CASES = load_cases()


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

    for tbl in expects.get("must_tables", []):
        assert tbl.lower() in sql, f"[{case['id']}] SQL 没用到表 {tbl}：{sql}"

    for kw in expects.get("must_keywords", []):
        assert kw.lower() in sql, f"[{case['id']}] SQL 缺关键词 {kw!r}：{sql}"

    for kw in expects.get("forbid_keywords", []):
        assert kw.lower() not in sql, f"[{case['id']}] SQL 命中禁止词 {kw!r}：{sql}"


def test_cases_loaded():
    """无 key 时也跑：保证 cases.yaml 至少被加载。"""
    assert len(CASES) >= 5, f"sample case 数 < 5，当前 {len(CASES)}"
    seen = set()
    for c in CASES:
        assert "id" in c and "question" in c, f"case 缺字段：{c}"
        assert c["id"] not in seen, f"重复 id：{c['id']}"
        seen.add(c["id"])
