"""tests/services/semantic/test_routing.py — v0.7.1 C4 flag-gated live 路由守护。

R-SL-20 flag 默认 off → None（0 metric/LLM 调用）· R-SL-14 未命中/编译失败 → None 回退 ·
命中 → AgentResult · R-SL-19 cost 归 sql_planner 桶（即使未命中）。
run_semantic_compile_step 经 monkeypatch（懒 import 同 module 对象 → patch 生效）；走 CI（import 链）。
"""
import pytest

from knot.services import cost_service, query_steps


@pytest.mark.asyncio
async def test_flag_off_returns_none_no_calls(monkeypatch):
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "false")
    result, audit = await query_steps.run_semantic_compile_step("q", None, "k", "", "", cost_service.empty_buckets(), 1, {})
    assert result is None and audit is None          # flag off → 无审计行


def _patch_catalog_metrics(monkeypatch, metrics):
    from knot.repositories import metric_repo
    from knot.services.agents import catalog as catalog_mod
    monkeypatch.setattr(catalog_mod, "current_catalog", lambda: {"catalog_id": 1, "tables": []})
    monkeypatch.setattr(metric_repo, "list_metrics", lambda cid: metrics)


@pytest.mark.asyncio
async def test_flag_on_no_metrics_returns_none(monkeypatch):
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    _patch_catalog_metrics(monkeypatch, [])
    result, audit = await query_steps.run_semantic_compile_step("q", None, "k", "", "", cost_service.empty_buckets(), 1, {})
    assert result is None and audit is None          # 无指标 → 无审计行


@pytest.mark.asyncio
async def test_flag_on_miss_returns_none_cost_to_sql_planner(monkeypatch):
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    _patch_catalog_metrics(monkeypatch, [{"name": "gmv", "base_object": "o"}])
    from knot.services.semantic import parser
    async def fake_parse(*a, **k):
        return {"logicform": None, "input_tokens": 5, "output_tokens": 7, "cost_usd": 0.003}
    monkeypatch.setattr(parser, "parse_to_logicform", fake_parse)
    buckets = cost_service.empty_buckets()
    result, audit = await query_steps.run_semantic_compile_step("q", None, "k", "", "", buckets, 1, {})
    assert result is None and audit is None          # parse 未命中 → 无 LogicForm → 无审计行
    assert buckets["sql_planner"]["cost"] == 0.003   # R-SL-19 即使未命中仍归桶


@pytest.mark.asyncio
async def test_flag_on_hit_returns_agentresult(monkeypatch):
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    _patch_catalog_metrics(monkeypatch, [{"name": "gmv", "base_object": "o"}])
    from knot.adapters.db import doris as db_connector
    from knot.core import time_resolver
    from knot.services import query_helper
    from knot.services.semantic import compiler, parser
    from knot.services.semantic.logicform import LogicForm
    async def fake_parse(*a, **k):
        return {"logicform": LogicForm(metrics=["gmv"]), "input_tokens": 5, "output_tokens": 7, "cost_usd": 0.003}
    monkeypatch.setattr(parser, "parse_to_logicform", fake_parse)
    monkeypatch.setattr(compiler, "compile_logicform", lambda lf, c, tc: "SELECT 1")
    monkeypatch.setattr(time_resolver, "resolve_time_context", lambda *a, **k: None)
    monkeypatch.setattr(query_helper, "assert_catalog_context", lambda *a, **k: None)
    monkeypatch.setattr(db_connector, "execute_query", lambda eng, sql: ([{"x": 1}], ""))
    result, audit = await query_steps.run_semantic_compile_step("q", "engine", "k", "", "", cost_service.empty_buckets(), 1, {})
    assert result is not None and result.sql == "SELECT 1" and result.rows == [{"x": 1}] and result.success
    assert audit and audit["logicform_json"] and audit["compile_error_reason"] == ""  # 命中 → 审计行 + canonical lf（R-SL-40）


@pytest.mark.asyncio
async def test_flag_on_compile_error_returns_none(monkeypatch):
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    _patch_catalog_metrics(monkeypatch, [{"name": "gmv", "base_object": "o"}])
    from knot.core import time_resolver
    from knot.services.semantic import compiler, parser
    from knot.services.semantic.logicform import LogicForm
    async def fake_parse(*a, **k):
        return {"logicform": LogicForm(metrics=["gmv"]), "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    monkeypatch.setattr(parser, "parse_to_logicform", fake_parse)
    def raise_compile(*a, **k):
        raise compiler.CompileError("ambiguous")
    monkeypatch.setattr(compiler, "compile_logicform", raise_compile)
    monkeypatch.setattr(time_resolver, "resolve_time_context", lambda *a, **k: None)
    result, audit = await query_steps.run_semantic_compile_step("q", "engine", "k", "", "", cost_service.empty_buckets(), 1, {})
    assert result is None                             # 编译失败 → None 回退（R-SL-14）
    assert audit and audit["compile_error_reason"] == "ambiguous"  # v0.7.3 near-miss → 审计行（诊断「为何回退」）
