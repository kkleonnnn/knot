"""会话与消息领域模型。

代表的真实实体：
  - Conversation ：用户在 ChatScreen 左侧栏看到的"一段连续对话"
  - Message      ：单次问答 = 用户问句 + Agent 生成的 SQL + 执行结果 + Presenter 解读

Conversation 1:N Message；删 Conversation 级联删 Message（conversation_repo 实现）。

Go 重写映射：internal/domain/conversation.go。
"""
from dataclasses import dataclass, field
from typing import Optional

# v0.4.2: 引用 agent.py 同层枚举（models→models 在 layered-architecture 内允许）
from knot.models.agent import AgentKind  # noqa: F401


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
    intent: Optional[str] = None  # v0.4.0 Clarifier 7 类意图；老消息为 None，前端走启发式
    # v0.4.2 成本归因分桶（agent_costs 总和 == cost_usd 由 cost_service.aggregate_agent_costs 保证 R-S8）
    agent_kind: str = "legacy"          # AgentKind: 老消息默认 'legacy'，新消息由 save_message 守护
    clarifier_cost: float = 0.0
    sql_planner_cost: float = 0.0
    fix_sql_cost: float = 0.0           # R-14 + Stage 4：fix_sql 独立桶
    presenter_cost: float = 0.0
    clarifier_tokens: int = 0
    sql_planner_tokens: int = 0
    fix_sql_tokens: int = 0
    presenter_tokens: int = 0
    recovery_attempt: int = 0           # R-14：含 fan-out reject + fix_sql retry
    created_at: Optional[str] = None
