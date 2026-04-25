import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Model catalogue ────────────────────────────────────────────────────
MODELS = {
    "claude-haiku-4-5-20251001": {
        "display":      "Claude Haiku 4.5",
        "provider":     "anthropic",
        "input_price":  0.80,
        "output_price": 4.00,
    },
    "claude-sonnet-4-6": {
        "display":      "Claude Sonnet 4.6",
        "provider":     "anthropic",
        "input_price":  3.00,
        "output_price": 15.00,
    },
    "gpt-4o-mini": {
        "display":      "GPT-4o Mini",
        "provider":     "openai",
        "input_price":  0.15,
        "output_price": 0.60,
    },
    "gpt-4o": {
        "display":      "GPT-4o",
        "provider":     "openai",
        "input_price":  2.50,
        "output_price": 10.00,
    },
    "gemini-2.0-flash": {
        "display":      "Gemini 2.0 Flash",
        "provider":     "gemini",
        "input_price":  0.10,
        "output_price": 0.40,
    },
    "deepseek-chat": {
        "display":      "DeepSeek V3",
        "provider":     "deepseek",
        "input_price":  0.27,
        "output_price": 1.10,
    },
}

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-haiku-4-5-20251001")

# ── Provider endpoints & keys ──────────────────────────────────────────
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

# ── SQLite path (absolute, relative to project root) ──────────────────
_project_root = Path(__file__).parent.parent
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(_project_root / "data" / "bi_agent.db"))

# ── v4 feature flags ───────────────────────────────────────────────────
AGENT_MAX_STEPS          = int(os.getenv("AGENT_MAX_STEPS",          "5"))
SCHEMA_FILTER_MAX_TABLES = int(os.getenv("SCHEMA_FILTER_MAX_TABLES", "10"))
RAG_TOP_K                = int(os.getenv("RAG_TOP_K",                "5"))
FEW_SHOT_MAX_EXAMPLES    = int(os.getenv("FEW_SHOT_MAX_EXAMPLES",    "4"))
