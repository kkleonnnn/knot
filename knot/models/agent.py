"""3-Agent 编排链路的契约形状（Clarifier / SQL Planner / Presenter）。

代表的真实实体：用户问 → Clarifier 理解 → SQL Planner 生成 → Presenter 解读
这条流水线上每一站之间传递的"信封"。本模块不含逻辑，只锁结构。

Go 重写映射：internal/domain/agent.go。每个 dataclass = 一个 struct。

注（v0.7.26 消歧）：SQL Planner 的结果形状 `AgentResult` 定义在
`services/agents/sql_planner.py`（query 路径实用 + v0.7.23/.25 呈现字段演进），
**非本模块** —— 曾在此有 vestigial 副本从未被消费，致双定义混淆（v0.7.23 加字段
误改本副本触发 test_routing 报错），已删。勿在此重建 AgentResult。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# v0.4.2: agent_kind 枚举锁（Stage 3-A 守护者要求 + 资深 Stage 4 拍板 fix_sql 独立桶）
# 'legacy' 仅供 v0.4.2 之前的老 message 持有；新 message save 时禁止显式传 'legacy'。
AgentKind = Literal["clarifier", "sql_planner", "fix_sql", "presenter", "legacy"]
VALID_AGENT_KINDS: tuple[str, ...] = ("clarifier", "sql_planner", "fix_sql", "presenter", "legacy")


@dataclass
class ClarifierOutput:
    """Clarifier agent 的输出（services/agents/orchestrator.run_clarifier 返回）。

    is_clear=True：可直接进 SQL Planner；refined_question 是消歧后的精确问句。
    is_clear=False：clarification_question 非空，前端提示用户补充信息后重发。

    intent（v0.4.0 新增）：7 类意图之一，决定前端 layout（INTENT_TO_HINT 映射）。
    Clarifier 输出缺失或非法时回退 'detail'（保守选择，至少不强行画图）。
    """
    is_clear: bool
    clarification_question: str | None
    refined_question: str
    analysis_approach: str = ""  # 一句话的分析思路提示，给下游 sql_planner 参考
    intent: str | None = None


@dataclass
class AgentStep:
    """SQL Planner ReAct 推理链的单步快照（Think → Act → Observe）。

    用于流式 SSE 把"Agent 思考过程"推送到前端 thinking panel。
    """
    step_num: int
    thought: str
    action: str  # execute_sql | describe_table | list_tables | search_schema | final_answer
    action_input: str
    observation: str
    timestamp: float = 0.0


@dataclass
class PresenterOutput:
    """Presenter agent 的输出（v0.2.2 起内联异常检查）。

    insight：自然语言洞察，前端在 SQL+表格下方渲染。
    confidence_reasoning：v0.3.0 路线图中"结论合理性自检"字段，当前 v0.3.x 默认空。
    follow_up_suggestions：建议追问列表，前端做 chip 展示。
    """
    insight: str
    confidence: str = "medium"
    confidence_reasoning: str = ""
    follow_up_suggestions: list = field(default_factory=list)
