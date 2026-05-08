"""error_translator — v0.4.4 BIAgentError → API 响应 dict 映射。

R-25 守护：每个 ErrorKind 显式标 is_retryable，前端按此渲染重试按钮：
- llm_failed (LLMNetwork/RateLimit) → True
- sql_exec_failed → True
- data_source_unavailable → True
- budget_exceeded → False（严禁前端给重试按钮，防无效尝试）
- llm_auth (config_missing) → False（admin 操作问题）
- sql_invalid → False（SQL guardrail 拒绝）
- config_missing → False
- internal → True（默认；兜底）

R-30 守护：service 层职责（不放 models 层；models 仅定义形状）。
"""
from __future__ import annotations

from bi_agent.models.errors import (
    BIAgentError,
    BudgetExceededError,
    BusinessDBError,
    ConfigMissingError,
    CrossGroupSQLError,
    DataSourceUnavailableError,
    LLMAuthError,
    LLMNetworkError,
    LLMRateLimitError,
    ProviderNotImplementedError,
    UnsafeSQLError,
)

# v0.4.4 ErrorKind 枚举（与前端 ErrorBanner KIND_STYLES 对齐）
# kind 是用户视角的错误类型；不同异常可映射到同一 kind（如 LLMNetwork + LLMRateLimit → llm_failed）
_TRANSLATIONS: list = [
    # (异常类, kind, user_message, is_retryable)
    (BudgetExceededError,        "budget_exceeded",
     "已达预算上限，请联系管理员调整阈值",                              False),
    (LLMAuthError,               "config_missing",
     "AI 服务认证失败，请联系管理员检查 API Key",                        False),
    (LLMRateLimitError,          "llm_failed",
     "AI 服务调用频率超限，请稍后重试",                                   True),
    (LLMNetworkError,            "llm_failed",
     "AI 服务暂时无法响应，请稍后重试",                                   True),
    (ProviderNotImplementedError, "config_missing",
     "未知的 AI provider，请联系管理员检查模型配置",                       False),
    (UnsafeSQLError,             "sql_invalid",
     "SQL 不安全或不符合规则（仅允许 SELECT，禁止写操作 / 笛卡尔积）",      False),
    (CrossGroupSQLError,         "sql_invalid",
     "跨数据源连接组的 SQL 不支持，请改写为单组查询",                       False),
    (BusinessDBError,            "sql_exec_failed",
     "业务库执行失败，请稍后重试或联系管理员",                              True),
    (DataSourceUnavailableError, "data_source_unavailable",
     "数据库未配置或连接失败，请联系管理员",                                True),
    (ConfigMissingError,         "config_missing",
     "服务配置缺失（API Key 或模型），请联系管理员",                        False),
]


def to_response(err: BIAgentError) -> dict:
    """统一 API 错误响应 shape（含 R-25 is_retryable）。

    返回结构：
        {
            "error_kind": "budget_exceeded" | "llm_failed" | ...,
            "user_message": "已达预算上限...",
            "is_retryable": False,
            "details": {...},  # err.meta 或 {"raw": str(err)}
        }
    """
    for cls, kind, user_message, is_retryable in _TRANSLATIONS:
        if isinstance(err, cls):
            details = getattr(err, "meta", None) or {"raw": str(err)[:200]}
            return {
                "error_kind": kind,
                "user_message": user_message,
                "is_retryable": is_retryable,
                "details": details,
            }
    # 兜底（含 BIAgentError 基类直接抛 + 未注册子类）
    return {
        "error_kind": "internal",
        "user_message": "服务出错，请稍后再试",
        "is_retryable": True,
        "details": {"raw": str(err)[:200]},
    }


def to_response_unknown(err: Exception) -> dict:
    """非 BIAgentError 兜底（未捕获的 Exception）。"""
    return {
        "error_kind": "internal",
        "user_message": "服务出错，请稍后再试",
        "is_retryable": True,
        "details": {"raw": str(err)[:200], "type": type(err).__name__},
    }
