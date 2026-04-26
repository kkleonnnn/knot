import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Model catalogue ────────────────────────────────────────────────────
# 命名约定：
#   - 直接 provider 通道（claude-*, gpt-*, gemini-*, deepseek-*）：兼容老配置
#   - OpenRouter 通道（带 vendor/ 前缀，如 anthropic/claude-opus-4）：v0.2.1 起统一推荐
# 新增模型按"OpenRouter 已覆盖的 7 家厂商"扩充：
#   Anthropic / OpenAI / Google / DeepSeek / Qwen / 智谱 GLM / MiniMax
MODELS = {
    # ── 直接 provider 通道（保留兼容） ──────────────────────────────
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

    # ── OpenRouter 通道：Anthropic ─────────────────────────────────
    "anthropic/claude-opus-4": {
        "display":      "Claude Opus 4 (OR)",
        "provider":     "openrouter",
        "input_price":  15.00,
        "output_price": 75.00,
    },
    "anthropic/claude-sonnet-4": {
        "display":      "Claude Sonnet 4 (OR)",
        "provider":     "openrouter",
        "input_price":  3.00,
        "output_price": 15.00,
    },
    "anthropic/claude-haiku-4.5": {
        "display":      "Claude Haiku 4.5 (OR)",
        "provider":     "openrouter",
        "input_price":  0.80,
        "output_price": 4.00,
    },

    # ── OpenRouter 通道：OpenAI ────────────────────────────────────
    "openai/gpt-4o": {
        "display":      "GPT-4o (OR)",
        "provider":     "openrouter",
        "input_price":  2.50,
        "output_price": 10.00,
    },
    "openai/gpt-4o-mini": {
        "display":      "GPT-4o Mini (OR)",
        "provider":     "openrouter",
        "input_price":  0.15,
        "output_price": 0.60,
    },
    "openai/o3-mini": {
        "display":      "o3-mini (OR)",
        "provider":     "openrouter",
        "input_price":  1.10,
        "output_price": 4.40,
    },

    # ── OpenRouter 通道：Google ────────────────────────────────────
    "google/gemini-2.0-flash-001": {
        "display":      "Gemini 2.0 Flash (OR)",
        "provider":     "openrouter",
        "input_price":  0.10,
        "output_price": 0.40,
    },
    "google/gemini-pro-1.5": {
        "display":      "Gemini 1.5 Pro (OR)",
        "provider":     "openrouter",
        "input_price":  1.25,
        "output_price": 5.00,
    },

    # ── OpenRouter 通道：DeepSeek ──────────────────────────────────
    "deepseek/deepseek-chat": {
        "display":      "DeepSeek V3 (OR)",
        "provider":     "openrouter",
        "input_price":  0.27,
        "output_price": 1.10,
    },
    "deepseek/deepseek-r1": {
        "display":      "DeepSeek R1 (OR)",
        "provider":     "openrouter",
        "input_price":  0.55,
        "output_price": 2.19,
    },

    # ── OpenRouter 通道：Qwen ──────────────────────────────────────
    "qwen/qwen-2.5-72b-instruct": {
        "display":      "Qwen 2.5 72B (OR)",
        "provider":     "openrouter",
        "input_price":  0.23,
        "output_price": 0.40,
    },
    "qwen/qwen-plus": {
        "display":      "Qwen Plus (OR)",
        "provider":     "openrouter",
        "input_price":  0.40,
        "output_price": 1.20,
    },

    # ── OpenRouter 通道：智谱 GLM ──────────────────────────────────
    "z-ai/glm-4.5": {
        "display":      "GLM-4.5 (OR)",
        "provider":     "openrouter",
        "input_price":  0.60,
        "output_price": 2.20,
    },
    "z-ai/glm-4.5-air": {
        "display":      "GLM-4.5 Air (OR)",
        "provider":     "openrouter",
        "input_price":  0.20,
        "output_price": 1.10,
    },

    # ── OpenRouter 通道：MiniMax ───────────────────────────────────
    "minimax/minimax-01": {
        "display":      "MiniMax-01 (OR)",
        "provider":     "openrouter",
        "input_price":  0.20,
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
