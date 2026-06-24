"""monitor_eval — 事件/规则评估引擎（v0.7.7 C2）。

取 metric 标量值（复用 compile_logicform metric-only LF + execute_query；_is_safe_sql DQL-only 收口
R-SL-68）+ 阈值/环比比较 → 命中判定。**0 LLM**（R-SL-70：纯确定性编译 + 算术，无 parser/presenter）。
fail-soft（R-SL-71/72）：engine None / compile 失败 / db error / 无值 → status=skipped（不中断整批）。

comparator：gt|lt|gte|lte|eq（阈值）/ pct_change_gt|pct_change_lt（环比异动 vs baseline_period）。
返 {hit, metric_value, status('fired'|'no_hit'|'skipped'), detail}。
"""
from __future__ import annotations

_THRESHOLD_OPS = {
    "gt": lambda v, t: v > t,
    "lt": lambda v, t: v < t,
    "gte": lambda v, t: v >= t,
    "lte": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
}


def _metric_scalar(metric_name: str, time_window: str, catalog: dict, engine, time_ctx):
    """编译 metric-only LogicForm → execute → 标量值。返 (value | None, error_str)。"""
    from knot.adapters.db import doris as db_connector
    from knot.services.semantic import compiler
    from knot.services.semantic.logicform import LogicForm

    lf = LogicForm(metrics=[metric_name], dimensions=[], time=time_window or "")
    try:
        sql = compiler.compile_logicform(lf, catalog, time_ctx)
    except compiler.CompileError as e:
        return None, f"编译失败: {e}"
    rows, db_error = db_connector.execute_query(engine, sql)   # R-SL-68 _is_safe_sql DQL-only 收口
    if db_error:
        return None, f"执行失败: {db_error}"
    if not rows:
        return None, "无数据"
    val = rows[0].get(metric_name)
    if val is None:
        val = next(iter(rows[0].values()), None)               # caliber AS name 兜底取首列
    if val is None:
        return None, "标量为空"
    return float(val), ""


def evaluate_monitor(monitor: dict, catalog: dict, engine, time_ctx) -> dict:
    """评估单 monitor（0 LLM）。engine None / 编译失败 / 无值 → skipped（fail-soft R-SL-71）。"""
    if engine is None:
        return {"hit": False, "metric_value": None, "status": "skipped", "detail": "数据源不可用"}

    cur, err = _metric_scalar(monitor["metric_name"], monitor["time_window"], catalog, engine, time_ctx)
    if err:
        return {"hit": False, "metric_value": None, "status": "skipped", "detail": err}

    comp = monitor["comparator"]
    thr = float(monitor["threshold"])

    if comp.startswith("pct_change"):
        # 环比：基准期取**同一 metric** 在 baseline_period 时间窗的值
        base, berr = (_metric_scalar(monitor["metric_name"], monitor["baseline_period"], catalog, engine, time_ctx)
                      if monitor.get("baseline_period") else (None, "无基准期"))
        if berr or base in (None, 0):
            return {"hit": False, "metric_value": cur, "status": "skipped",
                    "detail": berr or "基准期无值/为 0（无法算环比）"}
        pct = (cur - base) / base * 100.0
        hit = pct > thr if comp == "pct_change_gt" else pct < thr
        return {"hit": hit, "metric_value": cur, "status": "fired" if hit else "no_hit",
                "detail": f"环比 {pct:.1f}% {'>' if comp == 'pct_change_gt' else '<'} 阈值 {thr}（当期 {cur} vs 基准 {base}）"}

    op = _THRESHOLD_OPS.get(comp)
    if op is None:
        return {"hit": False, "metric_value": cur, "status": "skipped", "detail": f"未知 comparator: {comp}"}
    hit = op(cur, thr)
    return {"hit": hit, "metric_value": cur, "status": "fired" if hit else "no_hit",
            "detail": f"{cur} {comp} {thr}"}
