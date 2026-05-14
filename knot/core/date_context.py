"""date_context.py — 日期口径上下文（v0.2.3 / v0.6.1 升级）

v0.6.1 升级：date_context_block() 内部调用 time_resolver.resolve_time_context()
统一时间语义。R-PA-PB-6: sql_planner_prompts.py {date_context} 占位 byte-equal sustained
— 仅本模块内部升级，不改 prompt 字面。

v0.6.0 起包内 import 走 `from knot.core...`；time_resolver 是新增子模块。
"""

from knot.core.time_resolver import resolve_time_context
from knot.core.time_resolver import today as _resolver_today

# 重导出 — v0.4.x 业务代码仍 `from knot.core.date_context import today` 兼容
today = _resolver_today


def today_iso() -> str:
    return today().isoformat()


def date_context_block() -> str:
    """返回 prompt 用的日期口径块（多行字符串）。

    v0.6.1 起：内部走 time_resolver.resolve_time_context().prompt_block — 提供完整时间语义
    （含 5 类核心表达 + 同比基准 + 节假日上下文 + 约束）。

    v0.5.x 兼容：原 9 类相对日期表达（今天/昨天/最近 7/30 天/本周/上周/本月/上月）
    在 time_resolver prompt_block 中已含等价表达（"今年到目前"/"上周 ISO 周首"/"最近 7 天"等）。
    sql_planner_prompts.py {date_context} 占位 byte-equal sustained — 仅本函数返回值升级。
    """
    return resolve_time_context().prompt_block
