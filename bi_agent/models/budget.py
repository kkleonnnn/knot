"""预算配置领域模型（v0.4.3）。

代表的真实实体：admin 给某个 scope（global / user / agent_kind）设月度或单次调用
的成本/token 上限。超阈值时 'warn' 触发前端 banner 提示，'block' 触发 LLM 调用前
预检拒绝（仅 agent_kind/per_call_cost_usd 允许 block，避免误伤用户体验）。

R-16 优先级链（service 层负责）：User > Global（user 有独立预算时忽略 global）。
R-21 守护：scope_type='agent_kind' AND scope_value='legacy' 一律拒绝（legacy
是 v0.4.2 历史标记，给历史数据设预算无意义）。

Go 重写映射：internal/domain/budget.go。
"""
from dataclasses import dataclass
from typing import Literal, Optional

# v0.4.3 枚举锁（与 budget_repo / budget_service 校验对齐）
BudgetScope = Literal["user", "agent_kind", "global"]
BudgetType = Literal["monthly_cost_usd", "monthly_tokens", "per_call_cost_usd"]
BudgetAction = Literal["warn", "block"]

VALID_BUDGET_SCOPES: tuple[str, ...] = ("user", "agent_kind", "global")
VALID_BUDGET_TYPES: tuple[str, ...] = ("monthly_cost_usd", "monthly_tokens", "per_call_cost_usd")
VALID_BUDGET_ACTIONS: tuple[str, ...] = ("warn", "block")

# R-19 过滤起点：v0.4.2 上线日（YYYY-MM-DD）—— recovery_stats SQL 用 created_at >= 此日期
# 避免 v0.4.2 之前的 NULL agent_kind 历史数据污染趋势曲线
V042_RELEASE_DATE: str = "2026-05-08"


@dataclass
class Budget:
    """单条预算配置。"""
    id: int
    scope_type: str          # BudgetScope
    scope_value: str         # user_id 字符串 / agent_kind / 'all'
    budget_type: str         # BudgetType
    threshold: float         # 阈值（cost_usd 或 tokens 数值）
    action: str = "warn"     # BudgetAction; v0.4.3 默认 'warn'
    enabled: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
