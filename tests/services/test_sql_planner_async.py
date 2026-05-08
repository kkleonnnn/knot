"""tests/services/test_sql_planner_async.py — v0.4.4 arun_sql_agent ReAct async 守护测试。

覆盖：
- R-26-Senior：_acall_llm 在 budget block 时抛 BudgetExceededError，**不调** adapter
- R-30：BIAgentError 在 ReAct 循环中透传到调用方
- LLMNetworkError 不透传 → 转 final_error 由 AgentResult 汇报（v0.3.x sync 兼容）
"""
import pytest

from bi_agent.models.errors import BIAgentError, BudgetExceededError, LLMNetworkError
from bi_agent.repositories import budget_repo
from bi_agent.services.knot import sql_planner


@pytest.mark.asyncio
async def test_R26_senior_acall_llm_budget_block_before_adapter(tmp_db_path, monkeypatch):
    """R-26-Senior 端到端：sql_planner per_call block → _acall_llm 第一行抛
    BudgetExceededError；adapter 永不被调用。"""
    budget_repo.upsert("agent_kind", "sql_planner", "per_call_cost_usd", 0.000001, action="block")

    called = {"adapter": False}

    def _spy(provider):
        called["adapter"] = True
        raise RuntimeError("R-26-Senior 失败：adapter 在 block 后被调用")

    import bi_agent.adapters.llm.factory as factory_mod
    monkeypatch.setattr(factory_mod, "get_async_adapter", _spy)

    with pytest.raises(BudgetExceededError):
        await sql_planner._acall_llm(
            model_key="claude-haiku-4-5-20251001",
            api_key="fake",
            model_cfg={"provider": "anthropic", "input_price": 3.0, "output_price": 15.0},
            system_prompt="sys",
            messages=[{"role": "user", "content": "Q"}],
        )
    assert called["adapter"] is False, "R-26-Senior：adapter 不应被调用"


@pytest.mark.asyncio
async def test_R30_arun_sql_agent_propagates_budget_exceeded(tmp_db_path, monkeypatch):
    """R-30：ReAct 循环第一步遇 BudgetExceededError → 透传到调用方
    （不被 except Exception 转 final_error 静默吞）。"""
    async def _fail(*args, **kwargs):
        raise BudgetExceededError({"agent_kind": "sql_planner", "threshold": 0.001})

    monkeypatch.setattr(sql_planner, "_acall_llm", _fail)

    with pytest.raises(BudgetExceededError):
        await sql_planner.arun_sql_agent(
            question="昨天 GMV", schema_text="## tbl\n- col INT",
            engine=None, model_key="claude-haiku-4-5-20251001", api_key="fake",
            max_steps=3,
        )


@pytest.mark.asyncio
async def test_R30_arun_sql_agent_propagates_llm_network_error(monkeypatch):
    """R-30：LLMNetworkError 是 BIAgentError 子类，应透传给 api 层
    （error_translator 翻译为「AI 服务暂时无法响应」+ is_retryable=True）。
    取代 v0.3.x sync 把 raw network error 塞进 final_error 的兜底模式。"""
    async def _fail(*args, **kwargs):
        raise LLMNetworkError("timeout")

    monkeypatch.setattr(sql_planner, "_acall_llm", _fail)

    with pytest.raises(LLMNetworkError):
        await sql_planner.arun_sql_agent(
            question="Q", schema_text="schema", engine=None,
            model_key="claude-haiku-4-5-20251001", api_key="fake", max_steps=3,
        )


@pytest.mark.asyncio
async def test_arun_sql_agent_non_BIAgent_exception_becomes_final_error(monkeypatch):
    """非 BIAgentError（罕见的内部 bug 如 ValueError / KeyError）→ 转 final_error
    避免 ReAct 循环 1 步崩溃就 5xx 整个请求；保留 v0.3.x 兜底兼容。"""
    async def _broken(*args, **kwargs):
        raise ValueError("internal parser bug")

    monkeypatch.setattr(sql_planner, "_acall_llm", _broken)

    result = await sql_planner.arun_sql_agent(
        question="Q", schema_text="schema", engine=None,
        model_key="claude-haiku-4-5-20251001", api_key="fake", max_steps=3,
    )
    assert result.success is False
    assert "LLM 调用失败" in result.error


@pytest.mark.asyncio
async def test_arun_sql_agent_no_api_key_returns_error_result(monkeypatch):
    """无 API Key 立即返 AgentResult(success=False, error=...) 而非崩溃。"""
    result = await sql_planner.arun_sql_agent(
        question="Q", schema_text="schema", engine=None,
        model_key="claude-haiku-4-5-20251001",  # known anthropic
        api_key="",  # no key
        max_steps=3,
    )
    assert result.success is False
    assert "API Key" in result.error or "未设置" in result.error
