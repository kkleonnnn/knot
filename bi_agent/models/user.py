"""User 领域模型。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    id: int
    username: str
    role: str = "analyst"  # admin | analyst
    display_name: Optional[str] = None
    is_active: int = 1
    # 业务库默认连接（admin/analyst 入门期沿用，后续从 data_sources 派发）
    doris_host: Optional[str] = None
    doris_port: int = 9030
    doris_user: Optional[str] = None
    doris_database: Optional[str] = None
    default_source_id: Optional[int] = None
    # 用量统计
    monthly_tokens: int = 0
    monthly_cost_usd: float = 0.0
    avg_response_ms: int = 0
    query_count: int = 0
    created_at: Optional[str] = None


@dataclass
class AuthClaim:
    """JWT payload 解码结果。"""
    user_id: int
    username: str
    role: str
    exp: int = 0
