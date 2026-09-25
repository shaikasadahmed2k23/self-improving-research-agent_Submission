"""Central configuration: reads .env once and exposes typed settings."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Models
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_MODEL_STRONG = os.getenv("GROQ_MODEL_STRONG", "openai/gpt-oss-120b")
USE_STRONG_MODEL = _bool("USE_STRONG_MODEL", False)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Groq quotas are per model (free tier: ~200k tokens/day each), so the Groq models back each other
# up before falling back to Gemini (free tier gemini-2.5-flash: only ~20 requests/day).
GROQ_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GROQ_FALLBACK_MODELS", f"{GROQ_MODEL},{GROQ_MODEL_STRONG}").split(",") if m.strip()
]
# gpt-oss models are reasoning models: keep effort low and leave room for reasoning tokens,
# otherwise the token budget is spent on reasoning and the visible content comes back empty.
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 4096)

# Roles that switch to the strong model when USE_STRONG_MODEL is on
STRONG_ROLES = {"planner", "writer", "critic"}
# Roles that always use the strong model (the critic must catch subtle errors the 20B model makes)
ALWAYS_STRONG_ROLES = {"critic"}

# Agent limits
MAX_PLAN_STEPS = _int("MAX_PLAN_STEPS", 6)
MAX_REACT_ITERATIONS = _int("MAX_REACT_ITERATIONS", 4)
MAX_REVISIONS = _int("MAX_REVISIONS", 2)
CRITIC_PASS_SCORE = _int("CRITIC_PASS_SCORE", 7)
PAGE_CHAR_LIMIT = _int("PAGE_CHAR_LIMIT", 3000)

# Paths
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
MEMORY_DB_PATH = DATA_DIR / "agent_memory.db"


def groq_model_for(role: str) -> str:
    """Pick the Groq model for a node role (dev default: gpt-oss-20b; strong model opt-in)."""
    if role in ALWAYS_STRONG_ROLES or (USE_STRONG_MODEL and role in STRONG_ROLES):
        return GROQ_MODEL_STRONG
    return GROQ_MODEL
