"""knot.config — 配置统一收口（v0.3.0）

外部使用：
    from knot.config.settings import settings
    settings.SQLITE_DB_PATH, settings.DEFAULT_MODEL, ...

为兼容旧 `from config import X` 调用方，本子包同时把所有常量 re-export 到包级。
"""
from knot.config.settings import (  # noqa: F401
    AGENT_MAX_STEPS,
    DEFAULT_DB_DATABASE,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PASSWORD,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_MODEL,
    FEW_SHOT_MAX_EXAMPLES,
    MAX_RESULT_ROWS,
    MAX_RETRY_COUNT,
    MAX_TABLES_IN_SCHEMA,
    MAX_TOKENS_PER_QUERY,
    MODELS,
    PROVIDER_API_KEYS,
    PROVIDER_BASE_URLS,
    RAG_TOP_K,
    SCHEMA_FILTER_MAX_TABLES,
    SQL_TEMPERATURE,
    SQLITE_DB_PATH,
    STRICT_READONLY_GRANTS,
    settings,  # noqa: F401
)
