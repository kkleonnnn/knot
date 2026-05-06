"""bi_agent.config — 配置统一收口（v0.3.0）

外部使用：
    from bi_agent.config.settings import settings
    settings.SQLITE_DB_PATH, settings.DEFAULT_MODEL, ...

为兼容旧 `from config import X` 调用方，本子包同时把所有常量 re-export 到包级。
"""
from bi_agent.config.settings import settings  # noqa: F401
from bi_agent.config.settings import (  # noqa: F401
    MODELS,
    DEFAULT_MODEL,
    PROVIDER_BASE_URLS,
    PROVIDER_API_KEYS,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_PASSWORD,
    DEFAULT_DB_DATABASE,
    MAX_RESULT_ROWS,
    MAX_TABLES_IN_SCHEMA,
    MAX_TOKENS_PER_QUERY,
    SQL_TEMPERATURE,
    MAX_RETRY_COUNT,
    SQLITE_DB_PATH,
    AGENT_MAX_STEPS,
    SCHEMA_FILTER_MAX_TABLES,
    RAG_TOP_K,
    FEW_SHOT_MAX_EXAMPLES,
    STRICT_READONLY_GRANTS,
)
