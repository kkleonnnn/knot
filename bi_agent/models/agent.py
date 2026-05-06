"""3-Agent 流转契约：Clarifier / SQL Planner / Presenter 之间传递的形状。

Go 重写时这些 dataclass 1:1 对应 internal/domain/agent.go 的 struct。
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ClarifierOutput:
    """Clarifier agent 的输出契约。"""
    is_clear: bool
    clarification_question: Optional[str]
    refined_question: str
    analysis_approach: str = ""


@dataclass
class AgentStep:
    """SQL Planner 的 ReAct 单步记录。"""
    step_num: int
    thought: str
    action: str
    action_input: str
    observation: str
    timestamp: float = 0.0


@dataclass
class AgentResult:
    """SQL Planner 完整执行结果。"""
    success: bool
    sql: str
    rows: list = field(default_factory=list)
    explanation: str = ""
    confidence: str = "medium"  # high | medium | low
    error: str = ""
    steps: list = field(default_factory=list)  # list[AgentStep]
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class PresenterOutput:
    """Presenter agent 的输出契约。"""
    insight: str
    confidence: str = "medium"
    confidence_reasoning: str = ""
    follow_up_suggestions: list = field(default_factory=list)
