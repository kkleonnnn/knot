"""Conversation / Message 领域模型。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Conversation:
    id: int
    user_id: int
    title: str = "新对话"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Message:
    id: int
    conversation_id: int
    question: Optional[str] = None
    sql_text: Optional[str] = None
    explanation: Optional[str] = None
    confidence: Optional[str] = None  # high | medium | low
    rows: list = field(default_factory=list)
    db_error: Optional[str] = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    retry_count: int = 0
    created_at: Optional[str] = None
