"""3-Agent system prompt 模板覆盖记录。

代表的真实实体：admin 在「Prompt 模板」面板对某个 agent 的 system prompt
做的整段覆盖（替代代码内置的 _CLARIFIER_SYS / _SQL_PLANNER_SYS / _PRESENTER_SYS）。

未填则走代码默认；填了即注入 services/prompt_service.get_prompt 替换默认。

Go 重写映射：internal/domain/prompt.go。
"""
from dataclasses import dataclass
from typing import Literal, Optional

AgentName = Literal["clarifier", "sql_planner", "presenter"]


@dataclass
class PromptTemplate:
    """单个 agent 的 system prompt 覆盖记录。

    支持占位符（如 {schema} / {history} / {date_block} / {business_rules}）；
    services/prompt_service 在装配 prompt 时按命名占位符 .format(**kwargs)。
    特殊占位符 {__default__}：在自定义内容中插入代码内置默认（用于"在默认基础上追加"模式）。
    """
    agent_name: str  # 实际取 AgentName 之一
    content: str
    updated_by: Optional[int] = None
    updated_at: Optional[str] = None
