"""knot/services/semantic/multi_base.py — 多 base 聚合编译（v0.7.13 抽 module；v0.7.11/.12 逻辑移入）。

多 base（≥2 聚合对象）→ 确定性 SQL：无维度 → 标量子查询入 SELECT（v0.7.11，0 JOIN）；
有维度 → 维度并集驱动 + LEFT JOIN 各聚合（v0.7.12 Option U，聚合后 JOIN）。

**返 raw SQL（不自 _guard）**：`_guard` + `is_cartesian` 留 compiler（跨 build path 统一应用；
test monkeypatch `compiler.is_cartesian`）；compiler `_build_sql` 多 base 分支 `_guard(build_multi_base_sql(...))`。
**import compile_helpers only，0 import compiler**（Contract 9 锁无环分层防循环 import）。
"""
from __future__ import annotations

from knot.services.semantic.compile_helpers import (
    _OP_SQL,
    _TIME_KEYS,
    CompileError,
    _is_derived,
    _json_list,
    _order_limit,
    _parse_lineage,
    _resolve_metric_date_col,
    _resolve_physical,
    _scalar_subquery,
)


def build_multi_base_sql(lf, metrics_by_name, tables, time_ctx) -> str:
    """多 base 聚合分发（R-SL-105；返 raw SQL，compiler 包 _guard）：无维度 → 标量；有维度 → 维度并集驱动。

    guards（having/window/qualify/filters → raise）二者共用 —— 单 base grain 概念 / 多 base 归属歧义；
    raise CompileError（混合架构优雅回退 LLM），非 assert（守护者 Stage 3 — -O 禁用守护 + 崩溃非回退）。
    """
    if lf.having or lf.window or lf.qualify or lf.filters:
        raise CompileError("多 base + having/window/qualify/filters → 回退（单 base grain 概念 / 归属歧义）")
    if lf.time and lf.time not in _TIME_KEYS:
        raise CompileError(f"未知 time 枚举 {lf.time!r}")
    if not lf.dimensions:
        return _build_scalar_sql(lf, metrics_by_name, tables, time_ctx)
    return _build_dimensional_sql(lf, metrics_by_name, tables, time_ctx)


def _build_scalar_sql(lf, metrics_by_name, tables, time_ctx) -> str:
    """多 base 标量聚合（R-SL-98~100）：每 metric → 独立标量子查询入 SELECT（FROM-less，0 JOIN）。
    基数 BY CONSTRUCTION：标量子查询各返 1 行 + FROM-less → 1 行；0 JOIN 无 fan-out，免疫 v0.7.2 基数坑。
    各子查询单 base alias `o`（免 _rewrite_caliber）。返 raw（compiler 包 _guard）。"""
    subs = [f"{_scalar_subquery(metrics_by_name[name], tables, time_ctx, lf.time)} AS {name}"
            for name in lf.metrics]   # v0.7.16 复用 _scalar_subquery（抽共享 byte-equal；保序 = SELECT 列序）
    return "SELECT " + ", ".join(subs) + _order_limit(lf)


def _build_dimensional_sql(lf, metrics_by_name, tables, time_ctx) -> str:
    """多 base + 维度（R-SL-106~109；Option U 维度并集驱动）：维度并集 driver + LEFT JOIN 各 metric 聚合
    → 对称不丢数据（FULL OUTER 语义用 UNION+LEFT 模拟，0 FULL OUTER，Doris-proven）。返 raw（compiler 包 _guard）。

    ⭐ per-metric agg（守护者 Stage 3）：每 metric 独立 agg + **自己的 filters**（同 base 不同 filter metric
    各自正确；per-base 合用 names[0] 会静默算错）。基数 BY CONSTRUCTION：driver 1 行/组合 + 各 agg 1 行/组合
    → LEFT JOIN on 维度 1:1 不膨胀。"""
    union_branches, agg_joins, sel_metrics = [], [], []
    for i, name in enumerate(lf.metrics):                     # per-metric（保序 t0/t1/…）
        m = metrics_by_name[name]                             # 存在性已由 _metric_bases 校验
        avail = set(_json_list(m.get("dimensions")))
        for d in lf.dimensions:                               # 共同维度：每 dim ∈ 该 metric 可用维度（R-SL-107）
            if d not in avail:
                raise CompileError(f"维度 {d!r} ∉ metric {name!r} 可用维度（多 base 需共同维度）→ 回退")
        physical = _resolve_physical(m["base_object"], tables)    # HTTP/未匹配 → raise
        where = [str(f) for f in _json_list(m.get("filters"))]    # ⭐ 各 metric 自己的 filters（非 names[0] 共用）
        if lf.time:
            date_col = _resolve_metric_date_col(m, sorted(avail))   # v0.7.17 显式 date_column 优先
            if date_col is None:
                raise CompileError(f"metric {name!r} base 无日期列但 lf.time 设定 → 回退")
            start, end = getattr(time_ctx, lf.time)
            where.append(f"o.{date_col} BETWEEN '{start}' AND '{end}'")
        dim_cols = ", ".join(f"o.{d}" for d in lf.dimensions)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        union_branches.append(f"SELECT DISTINCT {dim_cols} FROM {physical} o{w}")
        agg = f"SELECT {dim_cols}, {m['caliber']} AS {name} FROM {physical} o{w} GROUP BY {dim_cols}"
        a = f"t{i}"
        # NULL-dim：`=`（资深拍 — 业务维度 DWD 兜底非 NULL）；⚠️ OSS 部署若维度可空须升 `<=>`（守护者 Stage 3）
        on = " AND ".join(f"dim.{d} = {a}.{d}" for d in lf.dimensions)
        agg_joins.append(f" LEFT JOIN ({agg}) {a} ON {on}")
        sel_metrics.append(f"{a}.{name}")
    driver = "(" + " UNION ".join(union_branches) + ") dim"   # 维度并集（对称不丢）
    sel_dims = ", ".join(f"dim.{d}" for d in lf.dimensions)
    return f"SELECT {sel_dims}, {', '.join(sel_metrics)} FROM {driver}" + "".join(agg_joins) + _order_limit(lf)


def build_derived_sql(lf, metrics_by_name, tables, time_ctx) -> str:
    """派生指标标量编译（v0.7.16 R-SL-132~139；placement=multi_base 资深拍）：单 metric 派生 →
    `SELECT (left subq) <op> NULLIF(right subq, 0) AS name`（FROM-less，0 JOIN）。返 raw（compiler 包 _guard）。

    标量 gate（去 time —— time per-dep 注入已在 _scalar_subquery；filters 禁 — 下推 dep 歧义）。
    路由（compiler）保证 len(lf.metrics)==1 且该 metric 派生。
    """
    if lf.dimensions or lf.having or lf.window or lf.qualify or lf.outer or lf.filters:
        raise CompileError("派生指标仅标量（维度/having/window/qualify/outer/filters → 回退；维度派生留后续）")
    name = lf.metrics[0]
    return "SELECT " + _derived_expr(metrics_by_name[name], metrics_by_name, tables, time_ctx, lf.time) + f" AS {name}"


def _derived_expr(m, metrics_by_name, tables, time_ctx, lf_time) -> str:
    """派生表达式 `(left subq) <op> [NULLIF](right subq)`（R-SL-133/134/135）：op 白名单 + left/right
    解析注册表**原子** metric（单层防循环）+ divide → NULLIF 除零；left/right 标量子查询含 per-dep time。"""
    lin = _parse_lineage(m)                       # {op, left, right}
    op = _OP_SQL.get(lin["op"])
    if op is None:
        raise CompileError(f"未知派生 op {lin['op']!r}（白名单 {sorted(_OP_SQL)}）→ 回退")
    left_m, right_m = metrics_by_name.get(lin["left"]), metrics_by_name.get(lin["right"])
    if not left_m or not right_m:
        raise CompileError(f"派生 left/right ({lin['left']!r}/{lin['right']!r}) ∉ 注册表 → 回退")
    if _is_derived(left_m) or _is_derived(right_m):   # ⭐ 单层：left/right 须原子（嵌套留后续，免 DFS）
        raise CompileError("派生 left/right 须原子 metric（嵌套派生留后续）→ 回退")
    left = _scalar_subquery(left_m, tables, time_ctx, lf_time)
    right = _scalar_subquery(right_m, tables, time_ctx, lf_time)
    if lin["op"] == "divide":                     # ⭐ 除零防护
        right = f"NULLIF({right}, 0)"
    return f"{left} {op} {right}"
