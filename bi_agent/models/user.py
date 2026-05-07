"""用户与认证领域模型。

代表的真实实体：
  - User      ：登录系统并发起 BI 查询的人（admin / analyst 二元角色）
  - AuthClaim ：JWT payload 的解码结果（在请求生命周期内代表"当前调用者"）

Go 重写映射：internal/domain/user.go（type User struct + type AuthClaim struct）。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """系统用户。一条记录 = users 表的一行 = 一个真实人。

    用量统计字段（monthly_tokens / cost_usd / query_count / avg_response_ms）
    是 v0.2.5 cost 观测的累计快照，每次查询完毕由 user_repo.update_user_usage 累加。
    """
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
    """已通过 JWT 校验的调用者身份凭证。

    生命周期：仅存在于单次 HTTP 请求处理过程中（FastAPI Depends 注入），不持久化。
    上层 admin 路由用 role 字段做权限分流（require_admin）。
    """
    user_id: int
    username: str
    role: str
    exp: int = 0
