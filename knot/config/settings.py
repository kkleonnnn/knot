"""knot.config.settings — 集中加载 .env，导出 Settings 单例 + 常量。

设计原则（v0.3.0）：
  - 所有 os.getenv() 调用集中在本文件，业务代码不得直接读环境变量
  - 兼容期：保留模块级常量（MODELS/DEFAULT_MODEL/...）供老代码 `from knot.config import X`
  - 推荐写法：`from knot.config import settings; settings.DEFAULT_MODEL`
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Model catalogue ────────────────────────────────────────────────────
# v0.6.0.6 F-D 数据源：OpenRouter live API curl 2026-05-15 + 守护者 M-D6 数据核验
# - 14 OR entries 加 max_context (实测从 OR API)
# - 7 OR entries pricing 修正 (修正：haiku-4.5 / deepseek-chat / deepseek-r1 /
#   qwen-2.5-72b / qwen-plus / glm-4.5-air)
# - 删除 google/gemini-pro-1.5 (OR 已下架)
# - 6 个 direct provider 保留 (守护者 M-D1 / 资深 ack — 等 Day 28+ 三方会议拍板)
# - 长期由 model_catalog_live 表 + admin UI "同步 OR" 按钮 (F-D-6) 自治刷新
MODELS = {
    # 直接 provider 通道（保留兼容；max_context 无 — 直 API 走 provider 默认）
    "claude-haiku-4-5-20251001": {"display": "Claude Haiku 4.5",  "provider": "anthropic", "input_price": 0.80, "output_price": 4.00},
    "claude-sonnet-4-6":         {"display": "Claude Sonnet 4.6", "provider": "anthropic", "input_price": 3.00, "output_price": 15.00},
    "gpt-4o-mini":               {"display": "GPT-4o Mini",       "provider": "openai",    "input_price": 0.15, "output_price": 0.60},
    "gpt-4o":                    {"display": "GPT-4o",            "provider": "openai",    "input_price": 2.50, "output_price": 10.00},
    "gemini-2.0-flash":          {"display": "Gemini 2.0 Flash",  "provider": "gemini",    "input_price": 0.10, "output_price": 0.40},
    "deepseek-chat":             {"display": "DeepSeek V3",       "provider": "deepseek",  "input_price": 0.27, "output_price": 1.10},

    # OpenRouter 通道 (14 entries — 数据 OR live API 2026-05-15 实测)
    "anthropic/claude-opus-4":      {"display": "Claude Opus 4 (OR)",     "provider": "openrouter", "input_price": 15.00, "output_price": 75.00, "max_context": 200000},
    "anthropic/claude-sonnet-4":    {"display": "Claude Sonnet 4 (OR)",   "provider": "openrouter", "input_price": 3.00,  "output_price": 15.00, "max_context": 1000000},
    "anthropic/claude-haiku-4.5":   {"display": "Claude Haiku 4.5 (OR)",  "provider": "openrouter", "input_price": 1.00,  "output_price": 5.00,  "max_context": 200000},
    "openai/gpt-4o":                {"display": "GPT-4o (OR)",            "provider": "openrouter", "input_price": 2.50,  "output_price": 10.00, "max_context": 128000},
    "openai/gpt-4o-mini":           {"display": "GPT-4o Mini (OR)",       "provider": "openrouter", "input_price": 0.15,  "output_price": 0.60,  "max_context": 128000},
    "openai/o3-mini":               {"display": "o3-mini (OR)",           "provider": "openrouter", "input_price": 1.10,  "output_price": 4.40,  "max_context": 200000},
    "google/gemini-2.0-flash-001":  {"display": "Gemini 2.0 Flash (OR)",  "provider": "openrouter", "input_price": 0.10,  "output_price": 0.40,  "max_context": 1048576},
    "deepseek/deepseek-chat":       {"display": "DeepSeek V3 (OR)",       "provider": "openrouter", "input_price": 0.32,  "output_price": 0.89,  "max_context": 163840},
    "deepseek/deepseek-r1":         {"display": "DeepSeek R1 (OR)",       "provider": "openrouter", "input_price": 0.70,  "output_price": 2.50,  "max_context": 64000},
    "qwen/qwen-2.5-72b-instruct":   {"display": "Qwen 2.5 72B (OR)",      "provider": "openrouter", "input_price": 0.36,  "output_price": 0.40,  "max_context": 32768},
    "qwen/qwen-plus":               {"display": "Qwen Plus (OR)",         "provider": "openrouter", "input_price": 0.26,  "output_price": 0.78,  "max_context": 1000000},
    "z-ai/glm-4.5":                 {"display": "GLM-4.5 (OR)",           "provider": "openrouter", "input_price": 0.60,  "output_price": 2.20,  "max_context": 131072},
    "z-ai/glm-4.5-air":             {"display": "GLM-4.5 Air (OR)",       "provider": "openrouter", "input_price": 0.13,  "output_price": 0.85,  "max_context": 131072},
    "minimax/minimax-01":           {"display": "MiniMax-01 (OR)",        "provider": "openrouter", "input_price": 0.20,  "output_price": 1.10,  "max_context": 1000192},
    # v0.6.0.6 F-D 删除 google/gemini-pro-1.5 — OR API 已下架
}

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-haiku-4-5-20251001")

PROVIDER_BASE_URLS = {
    "anthropic":  os.getenv("ANTHROPIC_BASE_URL", ""),
    "openai":     os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "deepseek":   "https://api.deepseek.com/v1",
    "ollama":     "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

PROVIDER_API_KEYS = {
    "anthropic":  os.getenv("ANTHROPIC_API_KEY", ""),
    "openai":     os.getenv("OPENAI_API_KEY", ""),
    "gemini":     os.getenv("GEMINI_API_KEY", ""),
    "deepseek":   os.getenv("DEEPSEEK_API_KEY", ""),
    "ollama":     "ollama",
    "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
}

# ── Database defaults ──────────────────────────────────────────────────
DEFAULT_DB_HOST     = os.getenv("DB_HOST",     "localhost")
DEFAULT_DB_PORT     = int(os.getenv("DB_PORT", "9030"))
DEFAULT_DB_USER     = os.getenv("DB_USER",     "")
DEFAULT_DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DEFAULT_DB_DATABASE = os.getenv("DB_DATABASE", "")

# ── Safety limits ──────────────────────────────────────────────────────
MAX_RESULT_ROWS       = 500
MAX_TABLES_IN_SCHEMA  = 20
MAX_TOKENS_PER_QUERY  = 1024
SQL_TEMPERATURE       = 0
MAX_RETRY_COUNT       = 2

# ── SQLite path (absolute) ─────────────────────────────────────────────
_project_root = Path(__file__).parent.parent.parent
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(_project_root / "knot" / "data" / "knot.db"))

# ── Feature flags ──────────────────────────────────────────────────────
AGENT_MAX_STEPS          = int(os.getenv("AGENT_MAX_STEPS",          "5"))
SCHEMA_FILTER_MAX_TABLES = int(os.getenv("SCHEMA_FILTER_MAX_TABLES", "25"))
RAG_TOP_K                = int(os.getenv("RAG_TOP_K",                "5"))
FEW_SHOT_MAX_EXAMPLES    = int(os.getenv("FEW_SHOT_MAX_EXAMPLES",    "4"))
STRICT_READONLY_GRANTS   = os.getenv("STRICT_READONLY_GRANTS", "0") == "1"


@dataclass(frozen=True)
class Settings:
    """对象式访问入口（推荐新代码用 settings.X 而非 module.X）。"""
    DEFAULT_MODEL: str = DEFAULT_MODEL
    SQLITE_DB_PATH: str = SQLITE_DB_PATH
    DEFAULT_DB_HOST: str = DEFAULT_DB_HOST
    DEFAULT_DB_PORT: int = DEFAULT_DB_PORT
    DEFAULT_DB_USER: str = DEFAULT_DB_USER
    DEFAULT_DB_PASSWORD: str = DEFAULT_DB_PASSWORD
    DEFAULT_DB_DATABASE: str = DEFAULT_DB_DATABASE
    MAX_RESULT_ROWS: int = MAX_RESULT_ROWS
    MAX_TABLES_IN_SCHEMA: int = MAX_TABLES_IN_SCHEMA
    MAX_TOKENS_PER_QUERY: int = MAX_TOKENS_PER_QUERY
    SQL_TEMPERATURE: float = SQL_TEMPERATURE
    MAX_RETRY_COUNT: int = MAX_RETRY_COUNT
    AGENT_MAX_STEPS: int = AGENT_MAX_STEPS
    SCHEMA_FILTER_MAX_TABLES: int = SCHEMA_FILTER_MAX_TABLES
    RAG_TOP_K: int = RAG_TOP_K
    FEW_SHOT_MAX_EXAMPLES: int = FEW_SHOT_MAX_EXAMPLES
    STRICT_READONLY_GRANTS: bool = STRICT_READONLY_GRANTS


settings = Settings()
