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
    buckets = cost_service.empty_buckets()
    result, audit = await query_steps.run_semantic_compile_step("q", "engine", "k", "", "", buckets, 1, {})
    assert result is not None and result.sql == "SELECT 1" and result.rows == [{"x": 1}] and result.success
    assert audit and audit["logicform_json"] and audit["compile_error_reason"] == ""  # 命中 → 审计行 + canonical lf（R-SL-40）
    # v0.7.18 R-SL-147：AgentResult 携带 parse cost+token（修 P1；原置 0 → 顶层 token 汇总命中时漏 parse）。
    assert result.total_input_tokens == 5 and result.total_output_tokens == 7 and result.total_cost_usd == 0.003
    assert buckets["sql_planner"]["cost"] == 0.003   # cost 仍入桶（R-SL-19；top-level cost 取桶，无双计）


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


# ─── B6.4（v0.8.2）跨期对比「必堵」guard ────────────────────────────────
from knot.services.query_steps import _period_comparison_unrepresented  # noqa: E402
from knot.services.semantic.logicform import LogicForm  # noqa: E402

_B64_METRICS = [{"name": "gmv", "base_object": "o", "dimensions": '["date","city"]', "aliases": "[]"}]


@pytest.mark.parametrize("q", [
    "本周平台总盈亏，同比上周", "本月GMV环比上月", "和上周比", "跟上个月相比",
    "相较去年", "比去年多了多少", "今天 vs 昨天 GMV 对比", "本周和上周新增用户数对比", "GMV YoY",
])
def test_b64_reject_scalar_comparison(q):
    """curated 标记集内跨期对比 + LF 无 lag → 拒识（True）。"""
    assert _period_comparison_unrepresented(q, LogicForm(metrics=["gmv"]), _B64_METRICS) is True


def test_b64_preserve_lag_window():
    """环比 + lag 窗（date-series）→ 已表达 → 不拒（保留既有能力，守护者 scope）。"""
    lf = LogicForm(metrics=["gmv"], dimensions=["date"],
                   window=[{"func": "lag", "arg": "gmv", "order_by": [{"field": "date", "dir": "asc"}], "as_name": "prev"}])
    assert _period_comparison_unrepresented("GMV每日环比", lf, _B64_METRICS) is False


@pytest.mark.parametrize("q", ["本月各城市成交额", "近7天注册用户数", ""])
def test_b64_non_comparison_untouched(q):
    """非对比 question（含空）→ 不触（byte-equal 0 影响）。"""
    assert _period_comparison_unrepresented(q, LogicForm(metrics=["gmv"]), _B64_METRICS) is False


def test_b64_false_positive_guards():
    """§C 假阳护：循环比例/环比例/MoMo/metric 名含标记 → 不触。"""
    lf = LogicForm(metrics=["gmv"])
    assert _period_comparison_unrepresented("循环比例分析", lf, _B64_METRICS) is False
    assert _period_comparison_unrepresented("同比例统计", lf, _B64_METRICS) is False
    assert _period_comparison_unrepresented("MoMo商城销量", lf, _B64_METRICS) is False
    m2 = [{"name": "同比增长率", "base_object": "o", "dimensions": "[]", "aliases": "[]"}]
    assert _period_comparison_unrepresented("同比增长率是多少", LogicForm(metrics=["同比增长率"]), m2) is False  # metric 名扣除


def test_b64_novel_phrasing_is_known_residual():
    """⚠️ 守护者 B-2 诚实：curated regex 非穷尽 → novel 措辞逃逸 = **已知残余**（非断言=0；真闭合待根治 compare 字段）。

    锁定当前范围：此措辞表达对比意图但未进 curated 集 → guard 不触（残余泄漏），非 bug。
    """
    assert _period_comparison_unrepresented("这个月比起那个月如何", LogicForm(metrics=["gmv"]), _B64_METRICS) is False


@pytest.mark.asyncio
async def test_b64_reject_routes_to_near_miss_via_raw_question(monkeypatch):
    """集成：raw_question 含同比 + LF 无 lag → guard raise（try 内）→ near-miss 行 + 回退（engine=llm 无徽标）。

    守护者 B-3：guard 跑 **raw_question**（非 refined）—— 此测 refined='refined'（无同比）验 raw 驱动触发。
    """
    monkeypatch.setenv("KNOT_SEMANTIC_LAYER", "true")
    _patch_catalog_metrics(monkeypatch, [{"name": "platform_pnl", "base_object": "o", "dimensions": "[]", "aliases": "[]"}])
    from knot.core import time_resolver
    from knot.services.semantic import parser
    async def fake_parse(*a, **k):
        return {"logicform": LogicForm(metrics=["platform_pnl"], time="this_week"),
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    monkeypatch.setattr(parser, "parse_to_logicform", fake_parse)
    monkeypatch.setattr(time_resolver, "resolve_time_context", lambda *a, **k: None)
    result, audit = await query_steps.run_semantic_compile_step(
        "refined", "engine", "k", "", "", cost_service.empty_buckets(), 1, {},
        raw_question="本周平台总盈亏，同比上周",
    )
    assert result is None                                             # 拒识 → 回退 LLM（无「确定性编译」徽标）
    assert audit and "拒识回退" in audit["compile_error_reason"] and "B6.4" in audit["compile_error_reason"]
