"""tests/services/test_sql_planner_cartesian.py — v0.5.1 cartesian ReAct 集成测试。

覆盖红线：
- R-82 __REJECT_CARTESIAN__ 协议（_run_tool final_answer 分支前置检测）
- R-85 cartesian + fan-out 联合 → cartesian 优先（更基础错误）
- R-91 连续 3 次拒收强制终止（局部计数器与 max_iterations 共享预算）
- R-80 sqlglot 失败 fail-open（不阻断 SQL 业务流）
"""
from unittest.mock import patch

import pytest

from knot.services.agents import sql_planner


# ── R-82 单元：_run_tool final_answer 分支 cartesian 前置检测 ──────────
def test_R82_final_answer_cartesian_returns_reject():
    """旧式逗号 → __REJECT_CARTESIAN__ 反馈（不是 __FINAL__）。"""
    obs = sql_planner._run_tool(
        "final_answer", "SELECT * FROM users, orders", engine=None, schema_text=""
    )
    assert obs.startswith("__REJECT_CARTESIAN__:"), f"got: {obs[:60]}"
    assert "comma-join" in obs or "tables" in obs


def test_R82_final_answer_cross_join_returns_reject():
    obs = sql_planner._run_tool(
        "final_answer", "SELECT * FROM a CROSS JOIN b", engine=None, schema_text=""
    )
    assert obs.startswith("__REJECT_CARTESIAN__:")
    assert "CROSS JOIN" in obs


def test_R82_final_answer_normal_sql_returns_final():
    """合法 JOIN ON → __FINAL__（不被误杀）。"""
    obs = sql_planner._run_tool(
        "final_answer",
        "SELECT u.id FROM users u JOIN orders o ON u.id = o.user_id",
        engine=None,
        schema_text="",
    )
    assert obs.startswith("__FINAL__:")


# ── R-85 cartesian + fan-out 联合 → cartesian 优先 ────────────────────
def test_R85_cartesian_takes_priority_over_fan_out():
    """同时含旧式逗号（cartesian C1）+ ≥ 2 LEFT JOIN ≥ 2 聚合（fan-out）→
    cartesian 优先返（cartesian 是更基础错误）。"""
    sql = (
        "SELECT u.id, SUM(d.amt), SUM(t.amt) "
        "FROM users u, archive_users au "  # ← C1 旧式逗号
        "LEFT JOIN deposits d ON u.id = d.user_id "
        "LEFT JOIN deals t ON u.id = t.user_id "
        "WHERE u.id = au.id "
        "GROUP BY u.id"
    )
    obs = sql_planner._run_tool("final_answer", sql, engine=None, schema_text="")
    assert obs.startswith("__REJECT_CARTESIAN__:"), f"expected cartesian-first, got: {obs[:80]}"
    assert "fan-out" not in obs.lower()


# ── R-91 连续 3 次拒收强制终止 ────────────────────────────────────────
def test_R91_three_consecutive_cartesian_rejects_force_terminate():
    """mock 不收敛的 LLM（连续返 cartesian SQL）→ run_sql_agent 在 3 次拒收
    后强制 break，AgentResult.success=False + error 含"连续 3 次"。"""

    def fake_llm(model_key, api_key, model_cfg, system_prompt, messages):
        # 始终返同一个 cartesian SQL（LLM 无法收敛）
        text = (
            "Thought: 提交最终 SQL\n"
            "Action: final_answer\n"
            "Action Input: SELECT * FROM users, orders WHERE users.id = orders.user_id"
        )
        return text, 10, 5

    with patch.object(sql_planner, "_call_llm", side_effect=fake_llm):
        result = sql_planner.run_sql_agent(
            question="join 一下",
            schema_text="### users\n### orders",
            engine=None,
            model_key="claude-haiku-4-5-20251001",
            api_key="fake",
            max_steps=10,
        )

    assert result.success is False
    assert "连续 3" in result.error or "连续 3 次" in result.error
    # 共享 max_iterations 预算 — 3 次拒收即终止，不耗尽 max_steps=10
    assert len(result.steps) == 3, f"expected 3 reject steps, got {len(result.steps)}"


def test_R91_react_recovers_after_first_cartesian_reject():
    """mock 收敛的 LLM（第 1 步 cartesian → 第 2 步合法）→ ReAct 反馈成功，
    不触发 R-91 强制终止；final_sql 是第 2 步的合法 SQL。"""
    call_count = {"n": 0}

    def fake_llm(model_key, api_key, model_cfg, system_prompt, messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            text = (
                "Thought: 先随便写个\n"
                "Action: final_answer\n"
                "Action Input: SELECT * FROM users, orders"  # cartesian
            )
        else:
            text = (
                "Thought: 修正为 JOIN ON\n"
                "Action: final_answer\n"
                "Action Input: SELECT u.id FROM users u JOIN orders o ON u.id = o.user_id"
            )
        return text, 10, 5

    # mock execute_query → 不真连 DB（final_sql 通过后 sql_planner 会调一次）
    def fake_execute(engine, sql):
        return [{"id": 1}], None

    with patch.object(sql_planner, "_call_llm", side_effect=fake_llm), \
         patch.object(sql_planner.db_connector, "execute_query", side_effect=fake_execute):
        result = sql_planner.run_sql_agent(
            question="join 一下",
            schema_text="### users\n### orders",
            engine=None,
            model_key="claude-haiku-4-5-20251001",
            api_key="fake",
            max_steps=10,
        )

    assert result.success is True, f"reject 1 次后应收敛，got error={result.error!r}"
    assert "JOIN" in result.sql.upper()
    assert "," not in result.sql.split("FROM")[1].split("WHERE")[0]  # 无逗号 join


# ── R-80 sqlglot 失败 fail-open（业务不阻断）─────────────────────────
def test_R80_sqlglot_failure_does_not_block_legitimate_sql():
    """sqlglot import 失败 → is_cartesian fail-open；合法 SQL 仍走 __FINAL__
    路径（不被 cartesian 检测误拒）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "sqlglot" or name.startswith("sqlglot."):
            raise ImportError("simulated sqlglot missing")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        # 合法 SQL（无 C1 文本侧逗号触发）→ sqlglot 失败 fail-open → __FINAL__
        obs = sql_planner._run_tool(
            "final_answer",
            "SELECT u.id FROM users u JOIN orders o ON u.id = o.user_id",
            engine=None,
            schema_text="",
        )
        assert obs.startswith("__FINAL__:"), f"sqlglot 失败不应阻断合法 SQL，got: {obs[:60]}"


# ── R-82 async 路径同步行为 ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_R82_async_path_cartesian_reject_count_terminates():
    """async ReAct 循环也必须有 R-91 计数器（与 sync 同行为）。"""
    async def fake_acall(model_key, api_key, model_cfg, system_prompt, messages):
        text = (
            "Thought: 提交\n"
            "Action: final_answer\n"
            "Action Input: SELECT * FROM a, b"
        )
        return text, 10, 5

    with patch.object(sql_planner, "_acall_llm", side_effect=fake_acall):
        result = await sql_planner.arun_sql_agent(
            question="join",
            schema_text="### a\n### b",
            engine=None,
            model_key="claude-haiku-4-5-20251001",
            api_key="fake",
            max_steps=10,
        )

    assert result.success is False
    assert "连续 3" in result.error
    assert len(result.steps) == 3
