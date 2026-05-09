"""knot.models.errors — 领域异常树（v0.3.2 R-7）

设计原则：
  - models/ 是叶子节点，本文件**不得**依赖任何 knot 子包（含 core）
  - 异常类**只**定义形状，不在异常类内做日志/IO 副作用
  - 上层 services/adapters 抓到异常后由各层自行决定如何记录

Go 重写映射：
  internal/domain/errors.go (sentinel errors + 类型断言)
"""
from __future__ import annotations


class BIAgentError(Exception):
    """所有领域异常的基类。"""


# ── adapters / LLM ────────────────────────────────────────────────────
class ProviderNotImplementedError(BIAgentError):
    """未知的 LLM provider（不在已支持清单中）。

    抛出时机：adapters/llm/factory.get_adapter("typo-name") 等。
    上层应 catch 后给出 admin 友好提示：「请检查 admin/api-models 配置」。
    """

    def __init__(self, provider: str, supported: list | None = None):
        self.provider = provider
        self.supported = supported or []
        msg = f"未知 LLM provider: {provider!r}"
        if supported:
            msg += f"；当前支持: {', '.join(supported)}"
        super().__init__(msg)


class LLMAuthError(BIAgentError):
    """LLM API Key 鉴权失败（401/403）。预留给 adapters 抛出。"""


class LLMRateLimitError(BIAgentError):
    """LLM 调用频率超限（429）。"""


class LLMNetworkError(BIAgentError):
    """v0.4.4：LLM 调用网络错误（timeout / DNS / 5xx）。

    与 LLMAuthError / LLMRateLimitError 区分；is_retryable=True（前端可显示重试按钮）。
    """

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(f"LLM network error: {detail}" if detail else "LLM network error")


# ── adapters / DB ─────────────────────────────────────────────────────
class BusinessDBError(BIAgentError):
    """业务库基类异常。"""


class UnsafeSQLError(BusinessDBError):
    """SQL guardrail 拒绝执行（写操作 / stacked query 等）。"""


class CrossGroupSQLError(BusinessDBError):
    """跨连接组 SQL（多源场景下不允许跨组 join）。"""


class DataSourceUnavailableError(BIAgentError):
    """v0.4.4：admin 未配数据源 / 连接失败。"""


# ── services / 资源限制 ───────────────────────────────────────────────
class BudgetExceededError(BIAgentError):
    """v0.4.4：预算硬阈值阻断（block）。R-26-Senior：在 LLM 调用前抛。

    meta 含 {budget_type, agent_kind, threshold, estimated} 等元信息，
    error_translator 转 API 响应时透传给前端。
    """

    def __init__(self, meta: dict | None = None):
        self.meta = meta or {}
        super().__init__(f"Budget exceeded: {self.meta}")


class ConfigMissingError(BIAgentError):
    """v0.4.4：API Key 未配 / 模型未启用 / admin 配置缺失。"""


class AuditWriteError(BIAgentError):
    """v0.4.6 R-65：审计写入失败（INSERT 异常）。

    audit_service 内部 catch + logger.error 不上抛（R-47 fail-soft）；
    本类的存在是为保持错误树结构一致（避免 v0.4.4 services/errors.py
    重复造轮子的 trap），并为未来需要可重试的审计补录场景预留。"""
