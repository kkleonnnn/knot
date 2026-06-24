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
async def test_multi_base_scalar_returns_logicform(monkeypatch):
    """v0.7.11：标量多 base（无维度）→ LogicForm（透传 compiler 标量子查询）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv","dau"]}')
    r = await parser.parse_to_logicform("本月 GMV 和活跃", [_GMV, _DAU], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].metrics == ["gmv", "dau"]


@pytest.mark.asyncio
async def test_multi_base_with_dims_returns_logicform(monkeypatch):
    """v0.7.12：多 base + 维度 → LogicForm（parser 放宽；compiler 共同维度 authoritative）。
    （v0.7.11 此 case parser pre-guard 返 None；v0.7.12 交 compiler 维度并集驱动编译。）"""
    _mock_allm(monkeypatch, '{"metrics":["gmv","dau"],"dimensions":["date"]}')
    r = await parser.parse_to_logicform("各天 GMV 和活跃", [_GMV, _DAU], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].dimensions == ["date"]


@pytest.mark.asyncio
async def test_malformed_json_returns_none(monkeypatch):
    _mock_allm(monkeypatch, "not json at all")
    r = await parser.parse_to_logicform("问", [_GMV], "model")
    assert r["logicform"] is None                 # 解析失败 → None 回退


# ─── _validate_hit / _build_prompt 纯 ────────────────────────────────

def test_validate_hit_single_object():
    assert parser._validate_hit(LogicForm(metrics=["gmv"]), [_GMV]) is True


def test_validate_hit_allows_multi_base():
    """v0.7.12：多 base 标量 + 多 base 带维度 → 都 True（compiler 共同维度 authoritative，非共同 → raise 回退）。"""
    assert parser._validate_hit(LogicForm(metrics=["gmv", "dau"]), [_GMV, _DAU]) is True               # 标量多 base
    assert parser._validate_hit(LogicForm(metrics=["gmv", "dau"], dimensions=["date"]), [_GMV, _DAU]) is True  # 多 base+维度（compiler 决）


def test_validate_hit_rejects_undefined():
    assert parser._validate_hit(LogicForm(metrics=["x"]), [_GMV]) is False


def test_build_prompt_injects_metrics_and_time_enums():
    p = parser._build_prompt([_GMV])
    assert "gmv" in p and "成交额" in p and "this_month_to_latest" in p


# ─── C4 跨对象维度（v0.7.2 narrowing：单 base 聚合 + 跨对象维度）──────

def test_prompt_allows_cross_object_dimensions():
    p = parser._build_prompt([_GMV])
    assert "可跨对象" in p                              # v0.7.2 维度可跨对象（prompt 放宽）


def test_prompt_teaches_multi_base_common_dimension():
    """v0.7.12：prompt 教 metrics 可引用不同对象 + 多对象带维度须「共同维度」（非共同回退）。"""
    p = parser._build_prompt([_GMV])
    assert "不同对象" in p and "共同维度" in p


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


# ─── v0.7.15 window frame（移动平均）prompt 教学 + 透传 R-SL-130 ──────────

@pytest.mark.asyncio
async def test_window_frame_extracted_through(monkeypatch):
    """R-SL-130：LLM 产出 window.frame → 透传 LogicForm.window[0]["frame"]（compiler _frame_clause 消费）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["date"],"window":'
               '[{"func":"avg","arg":"gmv","order_by":[{"field":"date","dir":"asc"}],"frame":{"preceding":6,"following":0},"as_name":"ma7"}]}')
    r = await parser.parse_to_logicform("GMV 7 日移动平均", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm)
    assert r["logicform"].window[0]["frame"] == {"preceding": 6, "following": 0}


def test_prompt_teaches_window_frame():
    """R-SL-130：prompt 教 frame 滑动窗口（仅 sum/avg + 结构化 preceding/following + unbounded）。"""
    p = parser._build_prompt([_GMV])
    assert "frame" in p and "移动平均" in p
    assert "preceding" in p and "unbounded" in p          # 结构化边界 + unbounded 枚举


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


# ─── v0.7.14 outer（结果再聚合）prompt 教学 + 透传 R-SL-123 ───────────────

@pytest.mark.asyncio
async def test_outer_extracted_through(monkeypatch):
    """R-SL-123：LLM 产出 outer → 透传 LogicForm.outer（compiler compile_logicform 消费）；_validate_hit 不变（outer 后处理）。"""
    _mock_allm(monkeypatch, '{"metrics":["gmv"],"dimensions":["city"],"having":["gmv > 10000"],"outer":{"func":"count"}}')
    r = await parser.parse_to_logicform("GMV 超 1 万的城市数", [_GMV], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].outer == {"func": "count"}


def test_prompt_teaches_outer_aggregate():
    """R-SL-123：prompt 教 outer 结果再聚合 + func 白名单 + arg alias-based。"""
    p = parser._build_prompt([_GMV])
    assert "outer" in p and "结果再聚合" in p
    assert "count|sum|avg|min|max" in p and "城市数" in p   # func 白名单 + 头号用例示例


# ─── v0.7.16 派生指标（占比/人均 = metric÷metric）R-SL-136 ────────────
_ARPU = {"name": "arpu", "display": "人均消费", "caliber": "", "base_object": "",
         "aliases": '["客单价"]', "dimensions": "", "lineage": '{"op":"divide","left":"gmv","right":"dau"}'}


def test_validate_hit_allows_derived():
    """⭐ R-SL-136：派生 metric base_object 空是设计 → _validate_hit 过（旧逻辑 `"" not in objs` 会误拒）。"""
    assert parser._validate_hit(LogicForm(metrics=["arpu"]), [_GMV, _DAU, _ARPU]) is True


def test_validate_hit_derived_skips_empty_base():
    """派生 + 原子混查：派生跳过空 base 判定，原子有 base → 过（compiler 决多派生回退）；空 base 原子仍拒。"""
    assert parser._validate_hit(LogicForm(metrics=["arpu", "gmv"]), [_GMV, _DAU, _ARPU]) is True   # 派生跳过 + gmv 有 base
    bad = {"name": "bad", "base_object": "", "lineage": ""}                                        # 非派生 + 空 base
    assert parser._validate_hit(LogicForm(metrics=["bad"]), [bad]) is False                        # 空 base 原子仍拒


def test_prompt_teaches_derived_scalar_only():
    """R-SL-136：prompt 教派生按 name 引用 + 仅标量（不配 dimensions/having/window）。"""
    p = parser._build_prompt([_GMV])
    assert "派生指标" in p and "仅支持标量" in p
    assert "客单价" in p or "ARPU" in p          # 占比/人均头号用例示例


@pytest.mark.asyncio
async def test_derived_extracted_through(monkeypatch):
    """⭐ R-SL-136：LLM 产出派生 metric → _validate_hit 过 → 透传 LogicForm（compiler 展开 metric÷metric）。"""
    _mock_allm(monkeypatch, '{"metrics":["arpu"]}')
    r = await parser.parse_to_logicform("本月人均消费", [_GMV, _DAU, _ARPU], "model")
    assert isinstance(r["logicform"], LogicForm) and r["logicform"].metrics == ["arpu"]
