"""knot/services/semantic/compile_helpers.py — LogicForm 编译器纯 helper leaf（v0.7.13 抽 module）。

compiler.py + multi_base.py 共用的纯函数/常量/异常（CompileError + time/date 常量 + base/dims/filters
解析 + ORDER BY/LIMIT 片段）。**纯 leaf：仅 import stdlib（json/re），0 import semantic 兄弟模块** →
无环分层（Contract 9 `semantic-compile-acyclic` 锁；防 multi_base→compiler 循环复发）。

CompileError 单定义于此；compiler.py re-export（`compiler.CompileError` 5+ 外部契约：
api/admin/logicform / query_steps / monitor_eval / test_routing），multi_base 也 import 同类对象。
"""
from __future__ import annotations

import json
import re

# TimeContext tuple 字段（time_resolver；lf.time 枚举 key）
_TIME_KEYS = {
    "this_year", "this_year_to_latest", "this_month", "this_month_to_latest",
    "last_week", "last_7_days_to_latest", "same_period_last_year",
    "today", "yesterday",            # v0.7.19 日粒度（含今天那天的单日窗口）
    "last_month", "last_year",       # v0.7.19 完整过去（→ ads 汇总）
}
# 日期列名 exact 模式（time 窗注入 regex fallback pass1；metric 未声明 date_column 时约定推断）
# ⚠️ v0.7.17 两遍解析 pass1 = 此 exact regex 逐字（含 stat_date/biz_date —— 删之引 order-drift）；
#    pass2 = `.endswith("_date")` 字符串法（非 `_date$` regex —— re.match 锚首使后缀失效，单 regex 是 NO-OP）。
_DATE_COL_EXACT_RE = re.compile(r"^(date|dt|ds|day|日期|stat_date|biz_date)$", re.I)
_DEFAULT_LIMIT = 1000  # lf.limit=0 时兜底


class CompileError(Exception):
    """编译无法干净确定性完成 → 调用方回退 LLM（混合架构 R-SL-14）。"""


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
    """从可用维度找日期列（time 窗注入 regex fallback）；无 → None（调用方按 lf.time 决定 raise）。

    v0.7.17 **两遍解析（strictly additive，守护者 Stage 3 承重修订）**：
    - pass1 = `_DATE_COL_EXACT_RE` 逐字（旧行为 byte-equal：旧 exact 命中 → 同列同序）；
    - pass2 = `.endswith("_date")` 兜底（仅 pass1 全 None 时填；修 `sta_date` gap）。
    单遍合并会让 `_date$` 列抢占旧 exact 列（`["amount_date","stat_date"]` 漂 `amount_date` = 选错日期列）。
    """
    for d in allowed_dims:                       # pass1：旧 exact regex（order + result 逐字保留）
        if _DATE_COL_EXACT_RE.match(str(d).strip()):
            return str(d).strip()
    for d in allowed_dims:                        # pass2：`_date` 后缀兜底（仅 pass1 全 miss 时）
        if str(d).strip().lower().endswith("_date"):
            return str(d).strip()
    return None


def _resolve_metric_date_col(m: dict, fallback_dims: list[str] | None = None) -> str | None:
    """metric 日期列解析（v0.7.17 R-SL-141）：**显式 `date_column` 优先**（注册表显式定义哲学）；
    未声明（空）→ regex fallback on dims（`fallback_dims` 给定用之，否则 m.dimensions）→ 保 byte-equal。"""
    explicit = (m.get("date_column") or "").strip()
    if explicit:
        return explicit
    dims = fallback_dims if fallback_dims is not None else _json_list(m.get("dimensions"))
    return _resolve_date_col(dims)


def _json_list(raw) -> list:
    """metric.filters / metric.dimensions 是 JSON list 字符串；解析兜底空。"""
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _order_limit(lf) -> str:
    """ORDER BY + LIMIT 片段（单/多对象共用）。

    R-SL-122：`lf.limit < 0` = 负哨兵 → **无 LIMIT 子句**（v0.7.14 outer-aggregate inner 聚合全部 groups；
    compile_logicform 在 outer+lf.limit==0 时 replace(lf, limit=-1) 设；LLM 出 limit≥0 → 存量 byte-equal）。
    """
    out = ""
    if lf.order_by:
        obs = [f"{o.get('field', '')} {'DESC' if str(o.get('dir', 'asc')).lower() == 'desc' else 'ASC'}"
               for o in lf.order_by if o.get("field")]
        if obs:
            out += " ORDER BY " + ", ".join(obs)
    if lf.limit and lf.limit < 0:   # 负哨兵 → 无 LIMIT（outer-aggregate inner 聚合全部）
        return out
    out += f" LIMIT {int(lf.limit) if lf.limit and lf.limit > 0 else _DEFAULT_LIMIT}"
    return out


def _frame_bound(v, side: str) -> str:
    """窗口 frame 边界（v0.7.15 R-SL-126 注入安全）：仅**非负 int**（排 bool）或 `"unbounded"`；0 → CURRENT ROW。
    side = 'PRECEDING' | 'FOLLOWING'。输出全受控（int repr + 字面），0 用户字符串裸拼。"""
    if isinstance(v, str) and v.strip().lower() == "unbounded":
        return f"UNBOUNDED {side}"
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:   # 排 bool（True→1 防误）+ 仅非负 int
        raise CompileError(f"frame 边界 {v!r} 须非负 int 或 'unbounded' → 回退")
    return "CURRENT ROW" if v == 0 else f"{v} {side}"


def _frame_clause(w: dict, takes_arg: bool, has_order_by: bool) -> str:
    """窗口 frame `ROWS BETWEEN <start> AND <end>`（v0.7.15 R-SL-127 gate）：
    仅 sum/avg 聚合窗口（ranking/lag/lead → raise）+ 需 ORDER BY（无 → raise）；边界经 `_frame_bound` 注入安全。"""
    if not takes_arg or str(w.get("func")) in ("lag", "lead"):
        raise CompileError(f"frame 仅 sum/avg 聚合窗口支持（func={w.get('func')!r}）→ 回退")
    if not has_order_by:
        raise CompileError("frame（ROWS BETWEEN）需 ORDER BY → 回退")
    f = w["frame"]
    return f"ROWS BETWEEN {_frame_bound(f.get('preceding'), 'PRECEDING')} AND {_frame_bound(f.get('following'), 'FOLLOWING')}"


def _scalar_subquery(m: dict, tables: list[dict], time_ctx=None, lf_time: str = "") -> str:
    """原子 metric 标量子查询 `(SELECT <caliber> FROM <physical> o [WHERE <filters>[AND time]])`（v0.7.16 抽共享）。

    **带括号无别名**；含 per-dep time 注入（lf_time 设 → 该 metric date_col 窗，无日期列 → raise）。
    multi_base `_build_scalar_sql`（+ AS name）与 derived `_derived_expr`（包算术）复用 → byte-equal v0.7.11。
    """
    physical = _resolve_physical(m["base_object"], tables)
    where = [str(f) for f in _json_list(m.get("filters"))]
    if lf_time:
        date_col = _resolve_metric_date_col(m)   # v0.7.17 显式 date_column 优先 + regex fallback
        if date_col is None:
            raise CompileError(f"metric {m.get('name')!r} base 无日期列但 time 设定 → 回退")
        start, end = getattr(time_ctx, lf_time)
        where.append(f"o.{date_col} BETWEEN '{start}' AND '{end}'")
    sub = f"SELECT {m['caliber']} FROM {physical} o"
    if where:
        sub += " WHERE " + " AND ".join(where)
    return f"({sub})"


# v0.7.16 派生指标 op 白名单 → SQL 运算符（R-SL-133 注入安全）
_OP_SQL = {"divide": "/", "multiply": "*", "add": "+", "subtract": "-"}


def _parse_lineage(m: dict):
    """metric.lineage → 派生定义 dict {op,left,right} 或 None（原子/空/非法）（v0.7.16）。"""
    raw = m.get("lineage")
    if not raw:
        return None
    if isinstance(raw, dict):
        d = raw
    else:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if isinstance(d, dict) and d.get("op") and d.get("left") and d.get("right"):
        return d
    return None


def _is_derived(m: dict) -> bool:
    """派生 metric = lineage 为合法派生定义 {op,left,right}（R-SL-132 判别）。"""
    return _parse_lineage(m) is not None
