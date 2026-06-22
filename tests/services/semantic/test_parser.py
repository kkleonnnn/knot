"""tests/services/semantic/test_parser.py — v0.7.1 C3 LogicForm 解析守护。

保守命中（引用 metric ∈ 注册表 + 单对象 → LogicForm；否则 None 回退）· R-SL-15 async ·
R-SL-19 成本归 sql_planner 桶（agent_kind="sql_planner"）· 无指标 → 0 LLM 调用。
async 测试 monkeypatch orchestrator._allm/_resolve（避真 LLM）；走 CI（import orchestrator）。
"""
import pytest

from knot.services.agents import orchestrator
from knot.services.semantic import parser
from knot.services.semantic.logicform import LogicForm

_GMV = {"name": "gmv", "display": "成交额", "caliber": "SUM(o.pay_amount)",
        "base_object": "shop.orders", "aliases": '["成交额"]', "dimensions": '["date","city"]'}
_DAU = {"name": "dau", "display": "活跃", "caliber": "COUNT(DISTINCT o.uid)",
        "base_object": "shop.users", "aliases": '["活跃"]', "dimensions": '["date"]'}


def _mock_allm(monkeypatch, json_text, captured=None):
    async def fake_allm(*args, agent_kind="clarifier", **kw):
        if captured is not None:
            captured["agent_kind"] = agent_kind
        return (json_text, 12, 34, 0.002)
    monkeypatch.setattr(orchestrator, "_allm", fake_allm)
    monkeypatch.setattr(orchestrator, "_resolve", lambda *a, **k: ("model", "key", {}))


# ─── 无指标 → 0 LLM ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_metrics_returns_none_no_llm(monkeypatch):
    called = {"n": 0}
    async def boom(*a, **k):
        called["n"] += 1
        return ("", 0, 0, 0.0)
    monkeypatch.setattr(orchestrator, "_allm", boom)
    r = await parser.parse_to_logicform("本月GMV", [], "model")
    assert r["logicform"] is None and r["cost_usd"] == 0.0
    assert called["n"] == 0                       # 无已定义指标 → 0 LLM 调用


# ─── 命中 / 未命中 / 校验 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hit_returns_logicform_and_sql_planner_bucket(monkeypatch):
    cap = {}
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["city"],"time":"this_month_to_latest"}', cap)
    r = await parser.parse_to_logicform("本月各城市成交额", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].metrics == ["gmv"]
    assert cap["agent_kind"] == "sql_planner"     # R-SL-19 复用 planning 桶
    assert r["cost_usd"] == 0.002                 # cost 透传供归桶


@pytest.mark.asyncio
async def test_empty_metrics_array_returns_none(monkeypatch):
    _mock_allm(monkeypatch, '{"metrics":[]}')     # LLM 判定未命中
    r = await parser.parse_to_logicform("随便问", [_GMV], "model")
    assert r["logicform"] is None and r["cost_usd"] == 0.002  # 仍归桶（LLM 已调用）


@pytest.mark.asyncio
async def test_undefined_metric_returns_none(monkeypatch):
    _mock_allm(monkeypatch, '{"metrics":["nonexistent"]}')
    r = await parser.parse_to_logicform("问", [_GMV], "model")
    assert r["logicform"] is None                 # 引用未定义 → None


@pytest.mark.asyncio
async def test_multi_object_returns_none(monkeypatch):
    _mock_allm(monkeypatch, '{"metrics":["gmv","dau"]}')
    r = await parser.parse_to_logicform("问", [_GMV, _DAU], "model")
    assert r["logicform"] is None                 # 跨对象 → None（单对象边界）


@pytest.mark.asyncio
async def test_malformed_json_returns_none(monkeypatch):
    _mock_allm(monkeypatch, "not json at all")
    r = await parser.parse_to_logicform("问", [_GMV], "model")
    assert r["logicform"] is None                 # 解析失败 → None 回退


# ─── _validate_hit / _build_prompt 纯 ────────────────────────────────

def test_validate_hit_single_object():
    assert parser._validate_hit(LogicForm(metrics=["gmv"]), [_GMV]) is True


def test_validate_hit_rejects_multi_object():
    assert parser._validate_hit(LogicForm(metrics=["gmv", "dau"]), [_GMV, _DAU]) is False


def test_validate_hit_rejects_undefined():
    assert parser._validate_hit(LogicForm(metrics=["x"]), [_GMV]) is False


def test_build_prompt_injects_metrics_and_time_enums():
    p = parser._build_prompt([_GMV])
    assert "gmv" in p and "成交额" in p and "this_month_to_latest" in p
