"""收藏报表领域模型（v0.4.1）。

代表的真实实体：用户在 ChatScreen 把某条 message 的 SQL + 结果"钉"成
可复用的报表。每条 saved_report 是 message 的完全快照（去耦合）：
  - intent / display_hint  : v0.4.0 mapping 的快照，跨 mapping 演进仍稳
  - sql_text               : 冻结 SQL，重跑入口（不允许日期宏替换 — 资深 Stage 2 定调）
  - data_source_id         : R-S2 优先用此 source 重跑；NULL 则 fallback 当前默认 + warning
  - last_run_*             : 软限制 200 行的最近一次结果快照，秒开预览

上游 conversation / message / data_source 删除时本对象不级联（无硬 FK）；
source_message_id / data_source_id 变 dangling 是 R-S7 预期行为。

Go 重写映射：internal/domain/saved_report.go。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SavedReport:
    """一条收藏报表。所有字段都是 message snapshot 时的物化值，重跑
    只动 last_run_* 系列；intent / display_hint / sql_text / question 不可变。
    """
    id: int
    user_id: int
    title: str
    sql_text: str
    source_message_id: Optional[int] = None
    data_source_id: Optional[int] = None
    question: Optional[str] = None
    intent: Optional[str] = None              # v0.4.0 7 类之一；老消息 fallback 'detail'（service 层负责）
    display_hint: Optional[str] = None        # INTENT_TO_HINT 快照；前端 effectiveHint 优先级 #1
    pin_note: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_rows_json: Optional[str] = None  # JSON-encoded list[dict]；软限制 200 行
    last_run_truncated: int = 0               # 1 = rows 被截断
    last_run_ms: int = 0
    pinned_at: Optional[str] = None
