"""tests/services/test_error_translator.py — v0.4.4 R-25 / R-30 错误翻译。

覆盖：
- 每个具体异常类映射到对应 kind + 正确 is_retryable
- BudgetExceededError.meta 透传 details
- 兜底 BIAgentError 子类 + 未注册类 → internal
- 非 BIAgentError 异常走 to_response_unknown
"""
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
from bi_agent.services import error_translator


def test_R25_budget_exceeded_is_not_retryable():
    """R-25 守护：budget_exceeded → is_retryable=False（防无效尝试）。"""
    err = BudgetExceededError({"budget_type": "per_call_cost_usd", "agent_kind": "fix_sql",
                                "threshold": 0.001, "estimated": 0.005})
    r = error_translator.to_response(err)
    assert r["error_kind"] == "budget_exceeded"
    assert r["is_retryable"] is False
    # meta 透传
    assert r["details"]["budget_type"] == "per_call_cost_usd"
    assert r["details"]["estimated"] == 0.005


def test_R25_llm_network_is_retryable():
    err = LLMNetworkError("connection timeout")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "llm_failed"
    assert r["is_retryable"] is True


def test_R25_llm_rate_limit_is_retryable():
    err = LLMRateLimitError("429 rate limit")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "llm_failed"
    assert r["is_retryable"] is True


def test_R25_llm_auth_is_not_retryable():
    """admin 操作问题，重试无意义。"""
    err = LLMAuthError("invalid api key")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "config_missing"
    assert r["is_retryable"] is False


def test_R25_unsafe_sql_is_not_retryable():
    err = UnsafeSQLError("DROP detected")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "sql_invalid"
    assert r["is_retryable"] is False


def test_R25_cross_group_sql_maps_to_sql_invalid():
    err = CrossGroupSQLError("跨组 join")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "sql_invalid"
    assert r["is_retryable"] is False


def test_R25_business_db_error_is_retryable():
    err = BusinessDBError("table not found")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "sql_exec_failed"
    assert r["is_retryable"] is True


def test_R25_data_source_unavailable_is_retryable():
    err = DataSourceUnavailableError("connection refused")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "data_source_unavailable"
    assert r["is_retryable"] is True


def test_R25_provider_not_implemented_maps_to_config_missing():
    err = ProviderNotImplementedError("typo-provider", supported=["anthropic", "openrouter"])
    r = error_translator.to_response(err)
    assert r["error_kind"] == "config_missing"
    assert r["is_retryable"] is False


def test_R25_config_missing_is_not_retryable():
    err = ConfigMissingError("API Key missing")
    r = error_translator.to_response(err)
    assert r["error_kind"] == "config_missing"
    assert r["is_retryable"] is False


def test_unknown_BIAgent_subclass_falls_back_to_internal():
    """未注册的 BIAgentError 子类走兜底（kind=internal, is_retryable=True）。"""
    class _CustomBIError(BIAgentError):
        pass
    r = error_translator.to_response(_CustomBIError("xx"))
    assert r["error_kind"] == "internal"
    assert r["is_retryable"] is True
    assert "raw" in r["details"]


def test_to_response_unknown_handles_non_BIAgentError():
    """非 BIAgentError 异常（如 RuntimeError / ValueError）走 to_response_unknown。"""
    r = error_translator.to_response_unknown(ValueError("xxx"))
    assert r["error_kind"] == "internal"
    assert r["is_retryable"] is True
    assert r["details"]["type"] == "ValueError"


def test_subclass_priority_specific_over_general():
    """更具体的异常类优先匹配（如 UnsafeSQLError 是 BusinessDBError 子类，
    但 UnsafeSQLError 应映射到 sql_invalid 而非 sql_exec_failed）。"""
    err = UnsafeSQLError("DROP detected")
    r = error_translator.to_response(err)
    # UnsafeSQLError 在 _TRANSLATIONS 中先于 BusinessDBError 注册 → sql_invalid 优先
    assert r["error_kind"] == "sql_invalid"
    assert r["is_retryable"] is False
