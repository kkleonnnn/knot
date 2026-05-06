"""Few-shot 示例领域模型。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FewShotExample:
    id: int
    question: str
    sql: str
    type: str = ""
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
