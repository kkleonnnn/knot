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
}
# 日期列名模式（time 窗注入用；无 explicit date_column 字段 → 约定推断）
_DATE_COL_RE = re.compile(r"^(date|dt|ds|day|日期|stat_date|biz_date)$", re.I)
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
