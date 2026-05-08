"""tests/services/test_llm_client_async.py — v0.4.4 async LLM client 守护测试。

覆盖：
- R-26-Senior：budget block 在 LLM 请求前（早于 SDK 实例化）
- R-32：afix_sql 必须传 agent_kind='fix_sql'，cost 进 fix_sql 桶
- R-24：sync API（generate_sql / fix_sql）仍可调用（向后兼容）
"""
import pytest

from bi_agent.models.errors import BudgetExceededError
from bi_agent.repositories import budget_repo
from bi_agent.services import llm_client


@pytest.mark.asyncio
async def test_R26_senior_budget_block_raises_before_sdk_instantiation(tmp_db_path, monkeypatch):
    """R-26-Senior 守护：触发 block 时必须抛 BudgetExceededError，
    且 LLM adapter 永不被调用（一字节网络成本都不发生）。

    策略：admin 设 fix_sql per_call_cost_usd=0.000001/block；
    任何 LLM 调用都会被预估 cost 超阈触发 → block。
    monkeypatch get_async_adapter 验证未被调用。
    """
    budget_repo.upsert("agent_kind", "fix_sql", "per_call_cost_usd", 0.000001, action="block")

    called = {"adapter": False}

    def _spy_get_async_adapter(provider):
        called["adapter"] = True
        raise RuntimeError("R-26-Senior 失败：LLM adapter 在 budget block 之后被错误调用")

    monkeypatch.setattr(llm_client, "get_async_adapter", _spy_get_async_adapter)

    with pytest.raises(BudgetExceededError) as exc_info:
        await llm_client._ainvoke_via_adapter(
            "system", "user msg",
            model_key="claude-haiku-4-5-20251001",
            api_key="fake",
            model_cfg={"provider": "anthropic", "input_price": 3.0, "output_price": 15.0},
            provider="anthropic",
            agent_kind="fix_sql",
        )
    assert called["adapter"] is False, "R-26-Senior 守护失败：adapter 在 block 后被调用"
    # meta 透传 estimated / threshold
    meta = exc_info.value.meta
    assert meta.get("agent_kind") == "fix_sql"
    assert meta.get("threshold") == 0.000001


@pytest.mark.asyncio
async def test_R26_senior_no_budget_no_block(tmp_db_path, monkeypatch):
    """无预算配置时不应 block；adapter 正常被调用。"""
    called = {"adapter": False}

    class _StubAdapter:
        async def acomplete(self, req):
            from bi_agent.adapters.llm.base import LLMResponse
            called["adapter"] = True
            return LLMResponse(text='{"sql": "SELECT 1", "explanation": "", "confidence": "high"}',
                               input_tokens=10, output_tokens=5)

    monkeypatch.setattr(llm_client, "get_async_adapter", lambda p: _StubAdapter())

    result = await llm_client._ainvoke_via_adapter(
        "system", "user",
        model_key="claude-haiku-4-5-20251001",
        api_key="fake",
        model_cfg={"provider": "anthropic", "input_price": 3.0, "output_price": 15.0},
        provider="anthropic",
        agent_kind="sql_planner",
    )
    assert called["adapter"] is True
    assert result["sql"] == "SELECT 1"


@pytest.mark.asyncio
async def test_R32_afix_sql_passes_agent_kind_fix_sql(tmp_db_path, monkeypatch):
    """R-32：afix_sql 调 _ainvoke_via_adapter 时必须传 agent_kind='fix_sql'，
    使 budget 守护针对 fix_sql 桶；不可混入 sql_planner 桶。
    """
    captured = {"agent_kind": None}

    async def _spy(system_prompt, user_message, model_key, key, model_cfg, provider, *,
                   agent_kind="sql_planner"):
        captured["agent_kind"] = agent_kind
        return {"sql": "fixed", "explanation": "", "confidence": "high",
                "error": "", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    monkeypatch.setattr(llm_client, "_ainvoke_via_adapter", _spy)

    await llm_client.afix_sql(
        question="Q", schema_text="schema",
        failed_sql="SELECT bad", error_message="syntax",
        model_key="claude-haiku-4-5-20251001", api_key="fake",
    )
    assert captured["agent_kind"] == "fix_sql", (
        "R-32 失败：afix_sql 未传 agent_kind='fix_sql'；"
        "budget 守护与 cost 分桶将错配"
    )


@pytest.mark.asyncio
async def test_R32_agenerate_sql_uses_sql_planner_agent_kind(tmp_db_path, monkeypatch):
    """对偶守护：agenerate_sql 主路径 agent_kind 必须是 'sql_planner'。"""
    captured = {"agent_kind": None}

    async def _spy(system_prompt, user_message, model_key, key, model_cfg, provider, *,
                   agent_kind="sql_planner"):
        captured["agent_kind"] = agent_kind
        return {"sql": "x", "explanation": "", "confidence": "high",
                "error": "", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    monkeypatch.setattr(llm_client, "_ainvoke_via_adapter", _spy)

    await llm_client.agenerate_sql(
        question="Q", schema_text="schema",
        model_key="claude-haiku-4-5-20251001", api_key="fake",
    )
    assert captured["agent_kind"] == "sql_planner"


def test_R24_sync_api_still_alive_generate_sql_no_key(tmp_db_path):
    """R-24：sync generate_sql 路径在无 API key 时仍正常返 _error_result（不抛 ImportError /
    AttributeError 等 async 改造引入的回归）。"""
    result = llm_client.generate_sql(
        question="Q", schema_text="s",
        model_key="claude-haiku-4-5-20251001",  # 已知非 openrouter 模型
        api_key="", business_context="", history=[], openrouter_api_key="",
    )
    # 没 API Key → 返 error 而非崩溃
    assert "error" in result
    assert result["sql"] == ""


def test_R24_sync_api_still_alive_fix_sql_no_key(tmp_db_path):
    """R-24：sync fix_sql 路径同样 alive。"""
    result = llm_client.fix_sql(
        "Q", "s", "SELECT bad", "syntax",
        model_key="claude-haiku-4-5-20251001", api_key="",
    )
    assert "error" in result
    assert result["sql"] == ""
