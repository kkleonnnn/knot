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


def _build_sql(lf, metrics_by_name: dict[str, dict], tables: list[dict], time_ctx) -> str:
    """纯确定性 SQL 构建（可单测，不依赖 DB / LLM）。同 (lf, time_ctx) → byte-equal。"""
    base_object = _resolve_single_object(list(lf.metrics), metrics_by_name)
    physical = _resolve_physical(base_object, tables)

    # 可用维度 = 该对象所有 metric 的 dimensions 并集（确定性排序仅用于校验，不影响 SELECT 序）
    allowed_dims: set[str] = set()
    for name in lf.metrics:
        allowed_dims.update(_json_list(metrics_by_name[name].get("dimensions")))

    # 请求维度 ⊆ 可用维度（保守；否则回退）
    for d in lf.dimensions:
        if d not in allowed_dims:
            raise CompileError(f"维度 {d!r} ∉ metric 可用维度 {sorted(allowed_dims)}")

    # SELECT: 维度（保序）+ metric caliber AS name（保序）
    select_parts = [f"o.{d}" for d in lf.dimensions]
    select_parts += [f"{metrics_by_name[name]['caliber']} AS {name}" for name in lf.metrics]

    # WHERE: metric 口径内置 filters（并集去重保序）+ lf.filters + time 窗
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

    # GROUP BY: 有维度即按维度分组（聚合 caliber 单对象语义）
    sql = f"SELECT {', '.join(select_parts)} FROM {physical} o"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if lf.dimensions:
        sql += " GROUP BY " + ", ".join(f"o.{d}" for d in lf.dimensions)
    if lf.order_by:
        obs = []
        for o in lf.order_by:
            field = o.get("field", "")
            direction = "DESC" if str(o.get("dir", "asc")).lower() == "desc" else "ASC"
            if field:
                obs.append(f"{field} {direction}")
        if obs:
            sql += " ORDER BY " + ", ".join(obs)
    sql += f" LIMIT {int(lf.limit) if lf.limit and lf.limit > 0 else _DEFAULT_LIMIT}"

    # R-SL-22 笛卡尔积守护兜底（防 caliber/dimension 错配产多表语法）；
    # fan-out 需 ≥2 JOIN，单对象 0 JOIN 不可能 → fan-out 守护留 v0.7.2 跨对象编译
    is_cart, reason = is_cartesian(sql)
    if is_cart:
        raise CompileError(f"编译产出触发笛卡尔积守护: {reason}")
    return sql


def compile_logicform(lf, catalog: dict, time_ctx) -> str:
    """主入口：从 active catalog 解析 metric（R-SL-21 catalog 隔离）→ 确定性编译 SQL。

    catalog = current_catalog() dict（含 catalog_id + tables）。仅取 active catalog 的 metric
    （`list_metrics(catalog_id)` — 非 None 全取，OOS-1 编译隔离）。
    """
    from knot.repositories import metric_repo  # 延迟 import（避 import-time 环 + 测试可 patch）

    catalog_id = catalog.get("catalog_id") or 1
    metrics_by_name = {m["name"]: m for m in metric_repo.list_metrics(catalog_id)}
    tables = catalog.get("tables") or []
    return _build_sql(lf, metrics_by_name, tables, time_ctx)
