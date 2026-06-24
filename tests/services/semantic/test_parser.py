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


# ─── C4 跨对象维度（v0.7.2 narrowing：单 base 聚合 + 跨对象维度）──────

def test_prompt_allows_cross_object_dimensions():
    p = parser._build_prompt([_GMV])
    assert "可跨对象" in p                              # v0.7.2 维度可跨对象（prompt 放宽）


@pytest.mark.asyncio
async def test_cross_object_dim_passes_through(monkeypatch):
    # LLM 产出 gmv(单 base) + region(跨对象维度) → _validate_hit 过（metrics 单 base）→ 透传给 compiler
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["region"]}')
    r = await parser.parse_to_logicform("各地区成交额", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm)
    assert r["logicform"].dimensions == ["region"]   # 跨对象维度不被 parser 拦（compiler C3 解析归属）


# ─── v0.7.8 HAVING（聚合后过滤）prompt 教学 + 透传 R-SL-80 ────────────

@pytest.mark.asyncio
async def test_having_extracted_through(monkeypatch):
    """LLM 产出 having（alias-based）→ 透传 LogicForm.having（compiler C1 消费）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["city"],"having":["gmv > 10000"]}')
    r = await parser.parse_to_logicform("GMV 超 1 万的城市", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].having == ["gmv > 10000"]


def test_prompt_teaches_alias_based_having():
    """R-SL-80：prompt 教 HAVING 强制 alias-based（引 metric name）+ 严禁原始口径/表前缀。"""
    p = parser._build_prompt([_GMV])
    assert "having" in p and "聚合后过滤" in p
    assert "metric name 作 alias" in p and "严禁" in p   # 强制 alias + 禁 raw o.col/裸 caliber


# ─── v0.7.9 窗口函数 prompt 教学 + 透传 R-SL-85/86 ───────────────────

@pytest.mark.asyncio
async def test_window_extracted_through(monkeypatch):
    """LLM 产出 window（alias-based）→ 透传 LogicForm.window（compiler C1 消费）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["region"],"window":'
               '[{"func":"row_number","partition_by":["region"],"order_by":[{"field":"gmv","dir":"desc"}],"as_name":"rk"}]}')
    r = await parser.parse_to_logicform("各地区 GMV 排名", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm)
    assert r["logicform"].window and r["logicform"].window[0]["func"] == "row_number"


def test_prompt_teaches_window_whitelist_alias_based():
    """R-SL-85/86：prompt 教 window func 白名单（dense_rank 非 rank_dense）+ alias-based partition/order。"""
    p = parser._build_prompt([_GMV])
    assert "window" in p and "row_number" in p and "dense_rank" in p   # 白名单含 dense_rank（真实函数名）
    assert "排名" in p and "alias-based" in p                          # 教学 + alias 强制


# ─── v0.7.10 分区 top-N（qualify）prompt 教学 + 透传 R-SL-95 ───────────

@pytest.mark.asyncio
async def test_qualify_extracted_through(monkeypatch):
    """LLM 产出 qualify（alias-based 引 window as_name）→ 透传 LogicForm.qualify（compiler C1 三层消费）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["region"],'
               '"window":[{"func":"row_number","partition_by":["region"],"order_by":[{"field":"gmv","dir":"desc"}],"as_name":"rk"}],'
               '"qualify":["rk <= 3"]}')
    r = await parser.parse_to_logicform("各地区 GMV 前 3", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm)
    assert r["logicform"].qualify == ["rk <= 3"]      # 透传（compiler 三层消费）


def test_prompt_teaches_qualify_alias_based():
    """R-SL-95：alias 正确性守护在 **parser 死线教学**（非 _is_safe_sql）—— prompt 教 qualify 引 window as_name + 严禁 raw。"""
    p = parser._build_prompt([_GMV])
    assert "qualify" in p and "分区 top-N" in p
    assert "as_name" in p and "严禁" in p              # alias 死线（引 window as_name）+ 禁 raw o.col/裸 caliber
