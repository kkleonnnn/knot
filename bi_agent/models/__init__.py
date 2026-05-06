"""bi_agent.models — 纯数据形状层（Leaf Node）

contract（import-linter 强制）：
    本包内任何模块**禁止**导入 bi_agent 任何其他子包（含 core）。
    只允许 stdlib + pydantic / dataclass 标准库。

Go 重写映射：本包 1:1 对应 Go 的 internal/domain/*.go。

显式 __all__（v0.3.0 R-1）：作为 Go 重写的"协议蓝图"，所有领域模型
在此显式导出，IDE 补全 + 静态分析友好。
"""

# ── 用户与认证 ─────────────────────────────────────────────────────────
# ── 3-Agent 流转契约 ───────────────────────────────────────────────────
from bi_agent.models.agent import (
    AgentResult,
    AgentStep,
    ClarifierOutput,
    PresenterOutput,
)

# ── 业务目录 ───────────────────────────────────────────────────────────
from bi_agent.models.catalog import Catalog, CatalogTable

# ── 会话与消息 ─────────────────────────────────────────────────────────
from bi_agent.models.conversation import Conversation, Message

# ── 业务库数据源 ───────────────────────────────────────────────────────
from bi_agent.models.data_source import DataSource

# ── Few-shot / Prompt / 知识库 / 设置 ──────────────────────────────────
from bi_agent.models.few_shot import FewShotExample
from bi_agent.models.knowledge import DocChunk, KnowledgeDoc

# ── LLM 调用与计费 ─────────────────────────────────────────────────────
from bi_agent.models.llm import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ProviderKind,
)
from bi_agent.models.prompt import AgentName, PromptTemplate
from bi_agent.models.setting import AppSetting, FileUpload
from bi_agent.models.user import AuthClaim, User

__all__ = [
    # user.py
    "User", "AuthClaim",
    # conversation.py
    "Conversation", "Message",
    # data_source.py
    "DataSource",
    # agent.py
    "ClarifierOutput", "AgentStep", "AgentResult", "PresenterOutput",
    # llm.py
    "ProviderKind", "LLMMessage", "LLMRequest", "LLMResponse", "ModelConfig",
    # catalog.py
    "CatalogTable", "Catalog",
    # few_shot.py
    "FewShotExample",
    # prompt.py
    "PromptTemplate", "AgentName",
    # knowledge.py
    "KnowledgeDoc", "DocChunk",
    # setting.py
    "AppSetting", "FileUpload",
]
