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

import json
import re

from knot.services.sql_validator import is_cartesian

# TimeContext tuple 字段（time_resolver；lf.time 枚举 key）
_TIME_KEYS = {
    "this_year", "this_year_to_latest", "this_month", "this_month_to_latest",
    "last_week", "last_7_days_to_latest", "same_period_last_year",
}
# 日期列名模式（time 窗注入用；无 explicit date_column 字段 → 约定推断）
_DATE_COL_RE = re.compile(r"^(date|dt|ds|day|日期|stat_date|biz_date)$", re.I)
# caliber 别名 `o.` 列引用前缀（v0.7.1 约定）；多对象重写为各对象 alias（R-SL-26）
_CALIBER_O_RE = re.compile(r"\bo\.")
_DEFAULT_LIMIT = 1000  # lf.limit=0 时兜底


class CompileError(Exception):
    """编译无法干净确定性完成 → 调用方回退 LLM（混合架构 R-SL-14）。"""


def _resolve_single_object(lf_metrics: list[str], metrics_by_name: dict[str, dict]) -> str:
    """全部引用 metric ∈ 注册表 + 共享同一 base_object（单对象 R-SL-18）；否则 raise。"""
    if not lf_metrics:
        raise CompileError("LogicForm 无 metric 引用")
    objs = set()
    for name in lf_metrics:
        m = metrics_by_name.get(name)
        if m is None:
            raise CompileError(f"未定义 metric: {name!r}")
        objs.add((m.get("base_object") or "").strip())
    if len(objs) != 1 or "" in objs:
        raise CompileError(f"非单对象（base_object={objs}）—— 跨对象 JOIN 留 v0.7.2")
    return objs.pop()


def _resolve_physical(base_object: str, tables: list[dict]) -> str:
    """base_object → 物理 `db.table`（匹配 catalog TABLES）；未匹配/HTTP 虚拟表 → raise。"""
    for t in tables:
        full = f"{t.get('db')}.{t.get('table')}"
        if base_object in (full, t.get("table")):
            if t.get("source_type") == "http":
                raise CompileError(f"base_object {base_object!r} 是 HTTP 虚拟表（跨源 OOS，v0.7.1 不编译）")
            return full
    raise CompileError(f"base_object {base_object!r} 未匹配 catalog 物理表")


def _resolve_date_col(allowed_dims: list[str]) -> str | None:
    """从可用维度找日期列（time 窗注入用）；无 → None（调用方按 lf.time 是否设定决定 raise）。"""
    for d in allowed_dims:
        if _DATE_COL_RE.match(str(d).strip()):
            return str(d).strip()
    return None


def _json_list(raw) -> list:
    """metric.filters / metric.dimensions 是 JSON list 字符串；解析兜底空。"""
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


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


def _order_limit(lf) -> str:
    """ORDER BY + LIMIT 片段（单/多对象共用）。"""
    out = ""
    if lf.order_by:
        obs = [f"{o.get('field', '')} {'DESC' if str(o.get('dir', 'asc')).lower() == 'desc' else 'ASC'}"
               for o in lf.order_by if o.get("field")]
        if obs:
            out += " ORDER BY " + ", ".join(obs)
    out += f" LIMIT {int(lf.limit) if lf.limit and lf.limit > 0 else _DEFAULT_LIMIT}"
    return out


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
    return f"{sqlfunc}({arg}) OVER ({' '.join(over)}) AS {w.get('as_name') or w.get('func')}"


def _finalize(inner_core: str, lf) -> str:
    """inner core（SELECT..GROUP BY）→ 最终 SQL。有 window → **两层**（F2：inner = core + having 不调 _order_limit；
    外层 `SELECT sub.*, <窗口列> FROM (inner) sub` + **整个 _order_limit**）；无 window → 单层 byte-equal（v0.7.1~.8 0 漂移）。"""
    inner = inner_core + _having_clause(lf)
    if lf.window:
        cols = ", ".join(_window_col(w) for w in lf.window)
        final = f"SELECT sub.*, {cols} FROM ({inner}) sub" + _order_limit(lf)
    else:
        final = inner + _order_limit(lf)
    return _guard(final)


def _guard(sql: str) -> str:
    """R-SL-22 笛卡尔积守护兜底（防 caliber/dimension/JOIN 错配产多表膨胀语法）。"""
    is_cart, reason = is_cartesian(sql)
    if is_cart:
        raise CompileError(f"编译产出触发笛卡尔积守护: {reason}")
    return sql


def _build_sql(lf, metrics_by_name: dict[str, dict], tables: list[dict], time_ctx, relations=None) -> str:
    """确定性 SQL 构建（纯，可单测）。单对象 → v0.7.1 byte-equal（R-SL-28）；跨对象维度 → 多表 JOIN。"""
    base = _resolve_single_object(list(lf.metrics), metrics_by_name)  # 单聚合 base（多 base → raise R-SL-31）
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
        date_col = _resolve_date_col(sorted(allowed_dims))
        if date_col is None:
            raise CompileError(f"lf.time={lf.time!r} 设定但无可解析日期列（回退 LLM 处理时间）")
        start, end = getattr(time_ctx, lf.time)
        where.append(f"o.{date_col} BETWEEN '{start}' AND '{end}'")
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
        date_col = _resolve_date_col(sorted(obj_dims.get(base, set())))
        if date_col is None:
            raise CompileError(f"lf.time={lf.time!r} 但 base 无日期列 → 回退")
        start, end = getattr(time_ctx, lf.time)
        where.append(f"{ba}.{date_col} BETWEEN '{start}' AND '{end}'")
    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if lf.dimensions:
        sql += " GROUP BY " + ", ".join(f"{aliases[owners[d]]}.{d}" for d in lf.dimensions)
    return _finalize(sql, lf)


def compile_logicform(lf, catalog: dict, time_ctx) -> str:
    """主入口：从 active catalog 解析 metric（R-SL-21 catalog 隔离）→ 确定性编译 SQL。

    catalog = current_catalog() dict（含 catalog_id + tables）。仅取 active catalog 的 metric
    （`list_metrics(catalog_id)` — 非 None 全取，OOS-1 编译隔离）。
    """
    from knot.repositories import metric_repo  # 延迟 import（避 import-time 环 + 测试可 patch）

    catalog_id = catalog.get("catalog_id") or 1
    metrics_by_name = {m["name"]: m for m in metric_repo.list_metrics(catalog_id)}
    tables = catalog.get("tables") or []
    relations = catalog.get("relations") or []   # R-SL-30/31 跨对象维度 JOIN + 基数 gate
    return _build_sql(lf, metrics_by_name, tables, time_ctx, relations)
