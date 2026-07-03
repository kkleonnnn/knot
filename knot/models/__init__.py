"""knot.models — 纯数据形状层（Leaf Node）

contract（import-linter 强制）：
    本包内任何模块**禁止**导入 knot 任何其他子包（含 core）。
    只允许 stdlib + pydantic / dataclass 标准库。

Go 重写映射：本包 1:1 对应 Go 的 internal/domain/*.go。

显式 __all__（v0.3.0 R-1）：作为 Go 重写的"协议蓝图"，所有领域模型
在此显式导出，IDE 补全 + 静态分析友好。

⚠️ [BLUEPRINT-ONLY]（v0.7.38 B3.1 标注）：本层部分 dataclass 是 **Go 重写契约锚点**，
Python 运行时**不实例化**（repositories 返 dict / api 用 Pydantic schema / services 装配 dict）。
下方 __all__ 中标 `[BLUEPRINT-ONLY]` 的 12 个 = 已 grounded 确认 0 外部实例化（保留作 Go 映射
+ 字段文档，非死码）；未标者 = LIVE（真被 import/实例化/类型标注，如 LLMRequest/DataSource/Budget）。
新增 dataclass 若从不实例化，请在此标 `[BLUEPRINT-ONLY]`（承 v0.7.26/.28 vestigial 清理精神：
真死码物理删，蓝图锚点显式标注）。
"""

# ── 异常树（v0.3.2 R-7） ───────────────────────────────────────────────
# ── 3-Agent 流转契约 ───────────────────────────────────────────────────
from knot.models.agent import (
    ClarifierOutput,
    PresenterOutput,
)

# ── 业务目录 ───────────────────────────────────────────────────────────
from knot.models.catalog import Catalog, CatalogTable

# ── 会话与消息 ─────────────────────────────────────────────────────────
from knot.models.conversation import Conversation, Message

# ── 业务库数据源 ───────────────────────────────────────────────────────
from knot.models.data_source import DataSource
from knot.models.errors import (
    AuditWriteError,
    BudgetExceededError,
    BusinessDBError,
    CatalogContextException,
    ConfigMissingError,
    CrossGroupSQLError,
    DataSourceUnavailableError,
    KnotError,
    LLMAuthError,
    LLMNetworkError,
    LLMRateLimitError,
    MetadataError,
    ProviderNotImplementedError,
    UnsafeSQLError,
)

# ── Few-shot / Prompt / 知识库 / 设置 ──────────────────────────────────
from knot.models.few_shot import FewShotExample
from knot.models.knowledge import DocChunk, KnowledgeDoc

# ── LLM 调用与计费 ─────────────────────────────────────────────────────
from knot.models.llm import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ProviderKind,
)
from knot.models.prompt import AgentName, PromptTemplate
from knot.models.setting import AppSetting, FileUpload
from knot.models.user import AuthClaim, User

__all__ = [
    # errors.py (v0.3.2 R-7 · v0.7.38 B3.4：14 error 全导出 + 基类 KnotError)
    "KnotError",
    "ProviderNotImplementedError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMNetworkError",
    "BusinessDBError",
    "UnsafeSQLError",
    "CrossGroupSQLError",
    "DataSourceUnavailableError",
    "MetadataError",
    "CatalogContextException",
    "BudgetExceededError",
    "ConfigMissingError",
    "AuditWriteError",
    # user.py
    "User", "AuthClaim",                       # AuthClaim [BLUEPRINT-ONLY]
    # conversation.py
    "Conversation", "Message",                 # Message [BLUEPRINT-ONLY]
    # data_source.py
    "DataSource",
    # agent.py（v0.7.26/.28 消歧：AgentResult + AgentStep 移除 — 真实定义在 services/agents/sql_planner.py）
    "ClarifierOutput", "PresenterOutput",      # 均 [BLUEPRINT-ONLY]
    # llm.py
    "ProviderKind", "LLMMessage", "LLMRequest", "LLMResponse", "ModelConfig",   # LLMMessage [BLUEPRINT-ONLY]
    # catalog.py
    "CatalogTable", "Catalog",                 # CatalogTable [BLUEPRINT-ONLY]
    # few_shot.py
    "FewShotExample",                          # [BLUEPRINT-ONLY]
    # prompt.py
    "PromptTemplate", "AgentName",             # PromptTemplate [BLUEPRINT-ONLY]
    # knowledge.py
    "KnowledgeDoc", "DocChunk",                # 均 [BLUEPRINT-ONLY]
    # setting.py
    "AppSetting", "FileUpload",                # 均 [BLUEPRINT-ONLY]
]
