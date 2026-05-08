"""tests/services/test_orchestrator_async.py — v0.4.4 arun_clarifier / arun_presenter 守护测试。

覆盖：
- arun_clarifier 走 _allm（agent_kind='clarifier'）
- arun_presenter 走 _allm（agent_kind='presenter'）
- BIAgentError（R-30）必须透传给上层；非领域异常被吞
- intent 兜底逻辑（v0.4.0）保留
"""
import pytest

from bi_agent.models.errors import BIAgentError, BudgetExceededError, LLMNetworkError
from bi_agent.services.knot import orchestrator


@pytest.mark.asyncio
async def test_R32_arun_clarifier_uses_agent_kind_clarifier(monkeypatch):
    """R-32：arun_clarifier 调 _allm 时必须传 agent_kind='clarifier'，
    使 cost 进 clarifier_cost 桶 + budget 守护针对 clarifier。"""
    captured = {"agent_kind": None}

    async def _spy_allm(model_key, key, cfg, system, messages, max_tokens=400, *,
                        agent_kind="clarifier"):
        captured["agent_kind"] = agent_kind
        return ('{"is_clear": true, "refined_question": "Q refined", "intent": "metric"}',
                100, 50, 0.001)

    monkeypatch.setattr(orchestrator, "_allm", _spy_allm)

    result = await orchestrator.arun_clarifier(
        question="昨天 GMV", schema_text="schema", history=[],
        model_key="claude-haiku-4-5-20251001", api_key="fake",
    )
    assert captured["agent_kind"] == "clarifier"
    assert result["is_clear"] is True
    assert result["intent"] == "metric"


@pytest.mark.asyncio
async def test_R32_arun_presenter_uses_agent_kind_presenter(monkeypatch):
    captured = {"agent_kind": None}

    async def _spy_allm(model_key, key, cfg, system, messages, max_tokens=400, *,
                        agent_kind="clarifier"):
        captured["agent_kind"] = agent_kind
        return ('{"insight": "test", "confidence": "high", "suggested_followups": []}',
                200, 100, 0.002)

    monkeypatch.setattr(orchestrator, "_allm", _spy_allm)

    result = await orchestrator.arun_presenter(
        question="Q", sql="SELECT 1", rows=[{"a": 1}],
        model_key="claude-haiku-4-5-20251001", api_key="fake",
    )
    assert captured["agent_kind"] == "presenter"
    assert result["insight"] == "test"


@pytest.mark.asyncio
async def test_R30_arun_clarifier_propagates_budget_exceeded(monkeypatch):
    """R-30：BudgetExceededError 必须透传给上层（不被 except Exception 吞）。"""
    async def _fail(*args, **kwargs):
        raise BudgetExceededError({"agent_kind": "clarifier", "threshold": 0.001})

    monkeypatch.setattr(orchestrator, "_allm", _fail)

    with pytest.raises(BudgetExceededError):
        await orchestrator.arun_clarifier(
            question="Q", schema_text="s", history=[],
            model_key="claude-haiku-4-5-20251001", api_key="fake",
        )


@pytest.mark.asyncio
async def test_R30_arun_presenter_propagates_llm_network_error(monkeypatch):
    """R-30：LLMNetworkError 必须透传给上层。"""
    async def _fail(*args, **kwargs):
        raise LLMNetworkError("timeout")

    monkeypatch.setattr(orchestrator, "_allm", _fail)

    with pytest.raises(LLMNetworkError):
        await orchestrator.arun_presenter(
            question="Q", sql="SELECT 1", rows=[],
            model_key="claude-haiku-4-5-20251001", api_key="fake",
        )


@pytest.mark.asyncio
async def test_arun_clarifier_swallows_non_BIAgent_exception(monkeypatch):
    """非领域异常（解析失败 / ValueError 等）静默 → 返默认结果（intent=detail 兜底）。
    与 sync run_clarifier 同模式。"""
    async def _broken(*args, **kwargs):
        raise ValueError("not a BIAgentError")

    monkeypatch.setattr(orchestrator, "_allm", _broken)

    result = await orchestrator.arun_clarifier(
        question="Q", schema_text="s", history=[],
        model_key="claude-haiku-4-5-20251001", api_key="fake",
    )
    # 默认值：is_clear=True, refined_question=question, intent=detail 兜底
    assert result["is_clear"] is True
    assert result["intent"] == "detail"  # DEFAULT_INTENT_FALLBACK
    assert result["cost_usd"] == 0


@pytest.mark.asyncio
async def test_R26_senior_arun_clarifier_blocks_before_adapter(tmp_db_path, monkeypatch):
    """R-26-Senior 端到端：clarifier 级 budget block 配置 → 抛 BudgetExceededError；
    确认 adapter.acomplete 永不被调用。"""
    from bi_agent.repositories import budget_repo
    budget_repo.upsert("agent_kind", "clarifier", "per_call_cost_usd", 0.000001, action="block")

    called = {"adapter": False}
    monkeypatch.setattr(orchestrator, "get_async_adapter" if False else "_resolve",
                        lambda *a, **kw: ("claude-haiku-4-5-20251001", "fake-key",
                                          {"provider": "anthropic", "input_price": 3.0,
                                           "output_price": 15.0}))

    # spy get_async_adapter — 通过 _allm 内部 import；用 import 路径替换
    import bi_agent.adapters.llm as adapters_pkg

    def _spy(provider):
        called["adapter"] = True
        raise RuntimeError("R-26-Senior 失败：adapter 在 budget block 后被调用")

    monkeypatch.setattr(adapters_pkg, "get_async_adapter", _spy)
    # 同时 patch orchestrator 模块级（_allm 内部 import 也要拦）
    import bi_agent.adapters.llm.factory as factory_mod
    monkeypatch.setattr(factory_mod, "get_async_adapter", _spy)

    with pytest.raises(BudgetExceededError):
        await orchestrator.arun_clarifier(
            question="Q", schema_text="s", history=[],
            model_key="claude-haiku-4-5-20251001", api_key="fake",
        )
    assert called["adapter"] is False, "R-26-Senior：adapter 不应被调用"
