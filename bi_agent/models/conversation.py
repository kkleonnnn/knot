"""会话与消息领域模型。

代表的真实实体：
  - Conversation ：用户在 ChatScreen 左侧栏看到的"一段连续对话"
  - Message      ：单次问答 = 用户问句 + Agent 生成的 SQL + 执行结果 + Presenter 解读

Conversation 1:N Message；删 Conversation 级联删 Message（conversation_repo 实现）。

Go 重写映射：internal/domain/conversation.go。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Conversation:
    """一个会话线索。title 由首条问句的前 30 字符自动生成（query.py），
    用户可在 admin 面板手工改名（PUT /api/conversations/{id}）。"""
    id: int
    user_id: int
    title: str = "新对话"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None  # 每次保存新 message 时刷新，用于侧栏排序


@dataclass
class Message:
    """一次完整的问答交互记录。

    字段语义：
      - question/sql_text/explanation/confidence: Agent 三件套输出
      - rows : 执行 SQL 拿到的结果集（前端渲染表格 + ECharts）
      - db_error : 业务库返回的错误信息；非空时 confidence=low
      - cost_usd / *_tokens : v0.2.5 cost 观测累计源
      - retry_count : SQL fix-on-failure 重试次数（MAX_RETRY_COUNT=2）
    """
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
