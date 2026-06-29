"""knot/services/semantic/compiler.py — LogicForm 单对象确定性编译器（v0.7.1 C2 · F3）。

`compile_logicform(lf, catalog, time_ctx) -> SQL`：**0 LLM 纯确定性**。
确定性铁律（R-SL-17）：`(LogicForm, 固定 time_ctx) → byte-equal SQL`。

保守原则（混合架构 R-SL-14）：只编译**能干净确定性编译的**；任何歧义 → raise `CompileError`
→ 调用方（F4）回退 LLM ReAct（零定义卖点保留）。触发 raise 的情形：
- 引用未定义 metric / 多对象（不同 base_object，单对象边界 R-SL-18）
- base_object 未匹配 catalog 物理表 / 是 HTTP 虚拟表（跨源 OOS）
- lf.time 设定但无可解析日期列 / 未知 time 枚举
- 编译产出过 is_cartesian 守护命中（R-SL-22；fan-out 需 ≥2 JOIN，单对象 0 JOIN 不适用 → 留 v0.7.2）
- 请求维度 ∉ metric 可用维度

caliber alias 固定 `o`（守护者 Stage 3 锁）：caliber 形如 `SUM(o.pay_amount)` → FROM `<db.table> o`。
"""
from __future__ import annotations

import re
from dataclasses import replace

from knot.services.semantic import multi_base
from knot.services.semantic.compile_helpers import (
    _TIME_KEYS,
    CompileError,
    _date_range_clause,
    _frame_clause,
    _is_derived,
    _json_list,
    _order_limit,
    _resolve_metric_date_col,
    _resolve_physical,
)
from knot.services.sql_validator import is_cartesian

# v0.7.13 抽 leaf：compile_helpers re-export CompileError/_TIME_KEYS 供 `compiler.X` 外部访问
# （5+ 生产 `except compiler.CompileError` + `compiler._TIME_KEYS`）；其余 helper 为 compiler 留守函数自用。
# caliber 别名 `o.` 列引用前缀（v0.7.1 约定）；多对象重写为各对象 alias（R-SL-26）
_CALIBER_O_RE = re.compile(r"\bo\.")


def _metric_bases(lf_metrics: list[str], metrics_by_name: dict[str, dict]) -> list[str]:
    """存在性校验 + 返回引用 metric 的 base_object 集（排序确定性）。任一未定义 / 无 base → raise。

    单 base（len==1）/ 多 base（len>1）由 `_build_sql` 按 len 分发（R-SL-98）：单 base 走 v0.7.1/.2
    路径；多 base 走标量聚合（R-SL-99）。v0.7.11 前是 `_resolve_single_object`（多 base 直接 raise）。
    """
    if not lf_metrics:
        raise CompileError("LogicForm 无 metric 引用")
    objs = set()
    for name in lf_metrics:
        m = metrics_by_name.get(name)
        if m is None:
            raise CompileError(f"未定义 metric: {name!r}")
        b = (m.get("base_object") or "").strip()
        if not b:
            raise CompileError(f"metric {name!r} 无 base_object")
        objs.add(b)
    return sorted(objs)


def _assign_aliases(objects: list[str]) -> dict[str, str]:
    """对象 → 确定性 alias。**单对象 → `o`**（R-SL-28 v0.7.1 byte-equal）；多对象 → 排序 `t0`/`t1`/…。"""
    objs = sorted(set(objects))
    if len(objs) == 1:
        return {objs[0]: "o"}
    return {o: f"t{i}" for i, o in enumerate(objs)}


def _rewrite_caliber(caliber: str, alias: str) -> str:
    """caliber 的 `o.` → `<alias>.`（R-SL-26 多对象 alias 归属）。

    **alias == `o` → 原样返回**（单对象 v0.7.1 byte-equal，0 改）。
    **regex（非 Stage 2 D4 LOCKED 的 sqlglot）—— 资深 2026-06-22 ratify**（守护者 Stage 3 复核 + 资深裁）：
    `\\bo\\.` 词边界只命中别名 `o` 的列前缀，不误伤 `foo.x`/`info.x`（`o` 非词首；见
    test_rewrite_caliber_word_boundary_no_false_hit）。回 sqlglot 反增 CI 迭代风险（重生成 caliber
    重格式化不可本地预测）+ 边际 robustness 仅惠及 flag-off 路径。
    ⚠️ **已知限制**：caliber 内字符串字面量含 `o.`（如 `'o.x'`）会被误改 —— 聚合口径几乎不含字面量，
    pathological + 基数 gate + 保守回退三重兜底；若未来口径引入字面量则回 sqlglot。
    """
    if alias == "o":
        return caliber
    return _CALIBER_O_RE.sub(f"{alias}.", caliber)


def _object_dims_map(metrics_by_name: dict[str, dict]) -> dict[str, set]:
    """{base_object: 该对象所有 metric 的 dims 并集}（跨对象维度归属用 R-SL-30）。"""
    out: dict[str, set] = {}
    for m in metrics_by_name.values():
        obj = (m.get("base_object") or "").strip()
        if obj:
            out.setdefault(obj, set()).update(_json_list(m.get("dimensions")))
    return out


def _resolve_dim_owner(dim: str, base: str, obj_dims: dict[str, set]) -> str:
    """维度归属唯一对象（R-SL-30）。base 有 → base；否则其他对象恰 1 拥有 → 它；0/≥2 → raise 回退。"""
    if dim in obj_dims.get(base, set()):
        return base
    owners = sorted(o for o, dims in obj_dims.items() if o != base and dim in dims)
    if len(owners) == 1:
        return owners[0]
    raise CompileError(f"维度 {dim!r} 归属歧义（owners={owners or '无'}）→ 回退")


def _having_clause(lf) -> str:
    """HAVING 片段（v0.7.8；GROUP BY 后 / ORDER BY 前）。**强制 alias-based** 引 metric alias（R-SL-80 —
    多对象 raw o. 不重写会断）；原始表达式镜像 filters，注入由 execute_query 顶 _is_safe_sql DQL-only 收口。"""
    return (" HAVING " + " AND ".join(str(h) for h in lf.having)) if lf.having else ""


# v0.7.9 窗口函数白名单（func key → 真实 SQL 函数, 是否带参）；R-SL-85 防注入 + 真实函数名（dense_rank→DENSE_RANK）
_WINDOW_FUNCS = {
    "row_number": ("ROW_NUMBER", False), "rank": ("RANK", False), "dense_rank": ("DENSE_RANK", False),
    "lag": ("LAG", True), "lead": ("LEAD", True), "sum": ("SUM", True), "avg": ("AVG", True),
}


def _window_col(w: dict) -> str:
    """单个窗口列 SQL（v0.7.9 R-SL-85/86）：`<FUNC>(<arg?>) OVER (PARTITION BY .. ORDER BY ..) AS <as_name>`。
    func 枚举白名单（未知 → CompileError 回退）；PARTITION/ORDER/arg 引 metric alias 或 dimension（alias-based —
    外层 OVER 引子查询列，免同层聚合表达式 + 多对象 o.→t0 重写）。"""
    fn = _WINDOW_FUNCS.get(str(w.get("func", "")))
    if fn is None:
        raise CompileError(f"未知窗口函数 {w.get('func')!r}（白名单 {sorted(_WINDOW_FUNCS)}）→ 回退")
    sqlfunc, takes_arg = fn
    arg = str(w.get("arg") or "") if takes_arg else ""
    over = []
    if w.get("partition_by"):
        over.append("PARTITION BY " + ", ".join(str(p) for p in w["partition_by"]))
    obs = [f"{o.get('field', '')} {'DESC' if str(o.get('dir', 'asc')).lower() == 'desc' else 'ASC'}"
           for o in (w.get("order_by") or []) if o.get("field")]
    if obs:
        over.append("ORDER BY " + ", ".join(obs))
    if w.get("frame"):   # v0.7.15 自定义 frame（ROWS BETWEEN）— gate + 注入安全在 _frame_clause
        over.append(_frame_clause(w, takes_arg, bool(obs)))
    return f"{sqlfunc}({arg}) OVER ({' '.join(over)}) AS {w.get('as_name') or w.get('func')}"


def _finalize(inner_core: str, lf) -> str:
    """inner core（SELECT..GROUP BY）→ 最终 SQL。**递进 byte-equal**：
    无 window → 单层（v0.7.1~.8 0 漂移）；window 无 qualify → 两层（v0.7.9 byte-equal：外层
    `SELECT sub.*, <窗口列> FROM (inner) sub`）；window + qualify → **三层**（v0.7.10 分区 top-N：
    外层 `SELECT * FROM (<两层>) win WHERE <qualify>`，QUALIFY 语义用外层 WHERE，不赌 Doris QUALIFY）。
    `_order_limit` 永远只在**最外层** append 一次（非生成后剥离 — R-SL-92）。"""
    if lf.qualify and not lf.window:
        raise CompileError("qualify 需 window 列（无 window 的分区过滤无意义）→ 回退")   # R-SL-94 严禁静默丢弃（否则返全量非 top-N）
    inner = inner_core + _having_clause(lf)
    if not lf.window:
        return _guard(inner + _order_limit(lf))                          # 单层 v0.7.1~.8 byte-equal
    cols = ", ".join(_window_col(w) for w in lf.window)
    win = f"SELECT sub.*, {cols} FROM ({inner}) sub"                     # 窗口两层（不调 _order_limit）
    if not lf.qualify:
        return _guard(win + _order_limit(lf))                            # 两层 v0.7.9 byte-equal
    qual = " AND ".join(str(q) for q in lf.qualify)                      # 三层：QUALIFY 语义 → 外层 WHERE
    return _guard(f"SELECT * FROM ({win}) win WHERE {qual}" + _order_limit(lf))


def _guard(sql: str) -> str:
    """R-SL-22 笛卡尔积守护兜底（防 caliber/dimension/JOIN 错配产多表膨胀语法）。"""
    is_cart, reason = is_cartesian(sql)
    if is_cart:
        raise CompileError(f"编译产出触发笛卡尔积守护: {reason}")
    return sql


def _build_sql(lf, metrics_by_name: dict[str, dict], tables: list[dict], time_ctx, relations=None) -> str:
    """确定性 SQL 构建（纯，可单测）。单对象 → v0.7.1 byte-equal（R-SL-28）；跨对象维度 → 多表 JOIN；
    多 base（≥2 聚合对象）→ 标量子查询入 SELECT（R-SL-98/99）；单 metric 派生 → metric÷metric 标量（R-SL-132~139）。"""
    if len(lf.metrics) == 1 and _is_derived(metrics_by_name.get(lf.metrics[0], {})):
        # v0.7.16 派生指标（先于 _metric_bases —— 派生 base_object 空会被 L54 raise 误杀；R-SL-136）
        return _guard(multi_base.build_derived_sql(lf, metrics_by_name, tables, time_ctx))
    bases = _metric_bases(list(lf.metrics), metrics_by_name)  # 存在性 + base 集（排序确定性）
    if len(bases) > 1:
        # v0.7.13：多 base 抽 multi_base.py（返 raw）；_guard 留 compiler 跨 build path 统一应用（R-SL-114）
        return _guard(multi_base.build_multi_base_sql(lf, metrics_by_name, tables, time_ctx))
    base = bases[0]
    obj_dims = _object_dims_map(metrics_by_name)
    owners = {d: _resolve_dim_owner(d, base, obj_dims) for d in lf.dimensions}
    if all(o == base for o in owners.values()):
        return _build_single_object_sql(lf, base, metrics_by_name, tables, time_ctx)
    return _build_multi_object_sql(lf, base, owners, metrics_by_name, obj_dims, tables, time_ctx, relations or [])


def _build_single_object_sql(lf, base_object, metrics_by_name, tables, time_ctx) -> str:
    """单对象（v0.7.1 逻辑，alias `o`）—— R-SL-28 byte-equal v0.7.1。"""
    physical = _resolve_physical(base_object, tables)
    allowed_dims: set[str] = set()
    for name in lf.metrics:
        allowed_dims.update(_json_list(metrics_by_name[name].get("dimensions")))
    for d in lf.dimensions:
        if d not in allowed_dims:
            raise CompileError(f"维度 {d!r} ∉ metric 可用维度 {sorted(allowed_dims)}")
    select_parts = [f"o.{d}" for d in lf.dimensions]
    select_parts += [f"{metrics_by_name[name]['caliber']} AS {name}" for name in lf.metrics]
    where: list[str] = []
    seen = set()
    for name in lf.metrics:
        for f in _json_list(metrics_by_name[name].get("filters")):
            if f not in seen:
                seen.add(f)
                where.append(str(f))
    for f in lf.filters:
        if f not in seen:
            seen.add(f)
            where.append(str(f))
    if lf.time:
        if lf.time not in _TIME_KEYS:
            raise CompileError(f"未知 time 枚举 {lf.time!r}")
        date_col = _resolve_metric_date_col(metrics_by_name[lf.metrics[0]], sorted(allowed_dims))
        if date_col is None:
            raise CompileError(f"lf.time={lf.time!r} 设定但无可解析日期列（回退 LLM 处理时间）")
        start, end = getattr(time_ctx, lf.time)
        where.append(_date_range_clause(f"o.{date_col}", start, end))   # v0.7.19 半开区间（datetime 列全天）
    sql = f"SELECT {', '.join(select_parts)} FROM {physical} o"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if lf.dimensions:
        sql += " GROUP BY " + ", ".join(f"o.{d}" for d in lf.dimensions)
    return _finalize(sql, lf)


def _build_multi_object_sql(lf, base, owners, metrics_by_name, obj_dims, tables, time_ctx, relations) -> str:
    """跨对象维度（单 base 聚合 + n:1/1:1 joined 维度表，base 不乘）。R-SL-30/31。"""
    from knot.services.semantic import joingraph
    objects = sorted({base} | set(owners.values()))
    path = joingraph.find_join_path(objects, relations)
    if path is None:
        raise CompileError(f"对象 {objects} 无唯一 JOIN 路径（≤3 表）→ 回退")
    if not joingraph.cardinality_safe(base, path):
        raise CompileError("JOIN 含 1:n/n:n/unknown 边（base 会被乘）→ 回退（R-SL-31）")
    aliases = _assign_aliases(path.tables)              # 多表 → t0/t1/…
    phys = {t: _resolve_physical(t, tables) for t in path.tables}
    ba = aliases[base]
    # SELECT：维度（归属对象 alias）+ caliber（base，重写 o→base_alias）
    select_parts = [f"{aliases[owners[d]]}.{d}" for d in lf.dimensions]
    select_parts += [f"{_rewrite_caliber(metrics_by_name[n]['caliber'], ba)} AS {n}" for n in lf.metrics]
    # FROM + JOIN（path 序，ON 用 alias）
    from_sql = f"{phys[path.tables[0]]} {aliases[path.tables[0]]}"
    for i, e in enumerate(path.edges):
        nt = path.tables[i + 1]
        from_sql += (f" JOIN {phys[nt]} {aliases[nt]} ON "
                     f"{aliases[e.left_table]}.{e.left_col} = {aliases[e.right_table]}.{e.right_col}")
    # WHERE：base filters（重写 o→base_alias）+ lf.filters + time（base date_col）
    where: list[str] = []
    seen = set()
    for n in lf.metrics:
        for f in _json_list(metrics_by_name[n].get("filters")):
            rf = _rewrite_caliber(str(f), ba)
            if rf not in seen:
                seen.add(rf)
                where.append(rf)
    for f in lf.filters:
        if str(f) not in seen:
            seen.add(str(f))
            where.append(str(f))
    if lf.time:
        if lf.time not in _TIME_KEYS:
            raise CompileError(f"未知 time 枚举 {lf.time!r}")
        date_col = _resolve_metric_date_col(metrics_by_name[lf.metrics[0]], sorted(obj_dims.get(base, set())))
        if date_col is None:
            raise CompileError(f"lf.time={lf.time!r} 但 base 无日期列 → 回退")
        start, end = getattr(time_ctx, lf.time)
        where.append(_date_range_clause(f"{ba}.{date_col}", start, end))   # v0.7.19 半开区间
    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if lf.dimensions:
        sql += " GROUP BY " + ", ".join(f"{aliases[owners[d]]}.{d}" for d in lf.dimensions)
    return _finalize(sql, lf)


# v0.7.14 结果再聚合（CTE 外层聚合）白名单（R-SL-120）
_OUTER_FUNCS = {"count", "sum", "avg", "min", "max"}


def _outer_expr(lf) -> str:
    """outer 聚合 `<FUNC>(<arg?>) AS result`（R-SL-120）：func 白名单 + count(*) 无 arg + 其他 func arg **alias-based ∈ metrics∪dimensions**（引 inner 输出列；严禁 raw caliber/表前缀，同 having R-SL-80）。"""
    func = str(lf.outer.get("func", "")).lower()
    if func not in _OUTER_FUNCS:
        raise CompileError(f"未知 outer 聚合 {func!r}（白名单 {sorted(_OUTER_FUNCS)}）→ 回退")
    arg = str(lf.outer.get("arg") or "")
    if func == "count" and not arg:
        return "COUNT(*) AS result"
    if not arg or arg not in set(lf.metrics) | set(lf.dimensions):   # 缺 arg / raw / 越界（alias-based 守护）
        raise CompileError(f"outer {func} arg {arg!r} 须非空且 ∈ metrics∪维度（alias-based）→ 回退")
    return f"{func.upper()}({arg}) AS result"


def compile_logicform(lf, catalog: dict, time_ctx) -> str:
    """主入口：从 active catalog 解析 metric（R-SL-21 catalog 隔离）→ 确定性编译 SQL。

    catalog = current_catalog() dict（含 catalog_id + tables）。仅取 active catalog 的 metric
    （`list_metrics(catalog_id)` — 非 None 全取，OOS-1 编译隔离）。
    v0.7.14：lf.outer → 结果再聚合 `WITH r AS (<现有编译>) SELECT <outer> FROM r`（_build_sql 不读 lf.outer，0 递归）。
    """
    from knot.repositories import metric_repo  # 延迟 import（避 import-time 环 + 测试可 patch）

    catalog_id = catalog.get("catalog_id") or 1
    metrics_by_name = {m["name"]: m for m in metric_repo.list_metrics(catalog_id)}
    tables = catalog.get("tables") or []
    relations = catalog.get("relations") or []   # R-SL-30/31 跨对象维度 JOIN + 基数 gate
    inner_lf = lf
    if lf.outer and not lf.limit:                # R-SL-122：outer 聚合全部（无显式 top-N）→ inner 无 LIMIT（哨兵 -1）
        inner_lf = replace(lf, limit=-1)
    inner = _build_sql(inner_lf, metrics_by_name, tables, time_ctx, relations)   # 复用全部现有覆盖作 CTE body
    if lf.outer:
        return _guard(f"WITH r AS ({inner}) SELECT {_outer_expr(lf)} FROM r")    # CTE 外层聚合（R-SL-119）
    return inner   # outer 空 → 无 wrap，存量 byte-equal
