"""Prompt 模板领域模型。"""
from dataclasses import dataclass
from typing import Literal, Optional

AgentName = Literal["clarifier", "sql_planner", "presenter"]


@dataclass
class PromptTemplate:
    agent_name: str  # 实际取 AgentName 之一
    content: str
    updated_by: Optional[int] = None
    updated_at: Optional[str] = None
