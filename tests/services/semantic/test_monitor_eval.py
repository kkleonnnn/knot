"""tests/services/semantic/test_monitor_eval.py — v0.7.7 C2 事件/规则评估引擎守护。

monkeypatch _metric_scalar（隔离 compile/DB，真编译由 test_compiler 覆盖）→ 测比较决策逻辑：
阈值 gt/lt/eq + 环比 pct_change + fail-soft skipped（engine None / 编译失败 / 基准 0 / 无基准期）。
0 LLM 结构性（monitor_eval 0 parser/presenter import）。
"""
from knot.services.semantic import monitor_eval as me


def _mon(**kw):
    base = dict(metric_name="gmv", comparator="lt", threshold=100.0, time_window="today", baseline_period="")
    base.update(kw)
    return base


def test_engine_none_skipped():
    r = me.evaluate_monitor(_mon(), {"catalog_id": 1}, engine=None, time_ctx=object())
    assert r["status"] == "skipped" and r["detail"] == "数据源不可用" and r["hit"] is False


def test_threshold_hit_and_no_hit(monkeypatch):
    monkeypatch.setattr(me, "_metric_scalar", lambda *a: (50.0, ""))          # 当期值 50
    assert me.evaluate_monitor(_mon(comparator="lt", threshold=100.0), {}, object(), object())["status"] == "fired"   # 50<100
    assert me.evaluate_monitor(_mon(comparator="gt", threshold=100.0), {}, object(), object())["status"] == "no_hit"  # 50>100 否
    monkeypatch.setattr(me, "_metric_scalar", lambda *a: (100.0, ""))
    assert me.evaluate_monitor(_mon(comparator="eq", threshold=100.0), {}, object(), object())["hit"] is True


def test_compile_fail_skipped(monkeypatch):
    monkeypatch.setattr(me, "_metric_scalar", lambda *a: (None, "编译失败: 未定义 metric"))
    r = me.evaluate_monitor(_mon(), {}, object(), object())
    assert r["status"] == "skipped" and "编译失败" in r["detail"]


def test_pct_change_hit(monkeypatch):
    # 当期 80 vs 基准 100 → 环比 -20%；pct_change_lt -10 → -20 < -10 命中
    monkeypatch.setattr(me, "_metric_scalar",
                        lambda metric, tw, *a: (80.0, "") if tw == "today" else (100.0, ""))
    r = me.evaluate_monitor(_mon(comparator="pct_change_lt", threshold=-10.0,
                                 time_window="today", baseline_period="last_period"), {}, object(), object())
    assert r["status"] == "fired" and r["metric_value"] == 80.0 and "环比 -20.0%" in r["detail"]


def test_pct_change_baseline_zero_skipped(monkeypatch):
    monkeypatch.setattr(me, "_metric_scalar",
                        lambda metric, tw, *a: (50.0, "") if tw == "today" else (0.0, ""))
    r = me.evaluate_monitor(_mon(comparator="pct_change_lt", threshold=-10.0,
                                 time_window="today", baseline_period="last_period"), {}, object(), object())
    assert r["status"] == "skipped" and "基准" in r["detail"]                 # 基准 0 无法算环比


def test_pct_change_no_baseline_skipped(monkeypatch):
    monkeypatch.setattr(me, "_metric_scalar", lambda *a: (80.0, ""))
    r = me.evaluate_monitor(_mon(comparator="pct_change_lt", threshold=-10.0, baseline_period=""),
                            {}, object(), object())
    assert r["status"] == "skipped" and "无基准期" in r["detail"]
