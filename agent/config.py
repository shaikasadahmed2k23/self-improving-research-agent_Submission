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
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# Models
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_MODEL_STRONG = os.getenv("GROQ_MODEL_STRONG", "openai/gpt-oss-120b")
USE_STRONG_MODEL = _bool("USE_STRONG_MODEL", False)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# NVIDIA NIM: fallback after the Groq models, before Gemini. (NIM retired gpt-oss-120b on 2026-09-03.)
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
# Groq quotas are per model (free tier: ~200k tokens/day each), so the Groq models back each other
# up before falling back to Gemini (free tier gemini-2.5-flash: only ~20 requests/day).
GROQ_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GROQ_FALLBACK_MODELS", f"{GROQ_MODEL},{GROQ_MODEL_STRONG}").split(",") if m.strip()
]
# A third Groq quota pool, tried after the models above (set empty to disable)
GROQ_MODEL_EXTRA = os.getenv("GROQ_MODEL_EXTRA", "qwen/qwen3.8-27b").strip()
if GROQ_MODEL_EXTRA and GROQ_MODEL_EXTRA not in GROQ_FALLBACK_MODELS:
    GROQ_FALLBACK_MODELS.append(GROQ_MODEL_EXTRA)
# Per-model output caps. qwen3.8-27b's free tier allows only 1000 output tokens/min, and max_tokens counts up front.
GROQ_MAX_TOKENS_CAP = {"qwen/qwen3.8-27b": 1000}
# gpt-oss models are reasoning models: keep effort low and leave room for reasoning tokens,
# otherwise the token budget is spent on reasoning and the visible content comes back empty.
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
# false = fail instead of switching models (for fair benchmark runs: a quota error stops the run, and no memory is written)
LLM_FALLBACKS = _bool("LLM_FALLBACKS", True)
# Rate limits: wait out short ones (per-minute caps) on the same model; longer waits (daily quota) go to the next model
LLM_RATE_RETRIES = _int("LLM_RATE_RETRIES", 4)
LLM_MAX_WAIT = _int("LLM_MAX_WAIT", 65)  # seconds
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 4096)

# Roles that switch to the strong model when USE_STRONG_MODEL is on
STRONG_ROLES = {"planner", "writer", "critic"}
# Roles that always use the strong model (the critic must catch subtle errors the 20B model makes)
ALWAYS_STRONG_ROLES = {"critic"}

# Development mode that spends fewer tokens: fewer steps, tool rounds and revisions, and tighter
# truncation of pages, snippets and step context. Saver values are caps: a smaller .env value still wins.
TOKEN_SAVER = _bool("TOKEN_SAVER", False)


def _limit(name: str, normal: int, saver: int) -> int:
    value = _int(name, normal)
    if not TOKEN_SAVER:
        return value
    return saver if value <= 0 else min(value, saver)  # 0 means "no limit"


# Agent limits
MAX_PLAN_STEPS = _limit("MAX_PLAN_STEPS", 6, 3)
MAX_REACT_ITERATIONS = _limit("MAX_REACT_ITERATIONS", 4, 3)
MAX_REVISIONS = _limit("MAX_REVISIONS", 2, 1)
CRITIC_PASS_SCORE = _int("CRITIC_PASS_SCORE", 7)
# What the LLM sees of a fetched page, each search snippet, and each earlier step's findings (executor context)
PAGE_CHAR_LIMIT = _limit("PAGE_CHAR_LIMIT", 3000, 1200)
SNIPPET_CHARS = _limit("SNIPPET_CHARS", 800, 300)
SEARCH_MAX_RESULTS = _limit("SEARCH_MAX_RESULTS", 5, 3)
STEP_CONTEXT_CHARS = _limit("STEP_CONTEXT_CHARS", 0, 600)  # 0 = no limit

# Paths
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
MEMORY_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", DATA_DIR / "agent_memory.db"))
TRACES_DIR = DATA_DIR / "traces"  # recorded runs (JSONL) for replay
SAMPLE_TRACES_DIR = ROOT_DIR / "samples" / "traces"  # committed demo traces


def groq_model_for(role: str) -> str:
    """Pick the Groq model for a node role (dev default: gpt-oss-20b; strong model opt-in)."""
    if role in ALWAYS_STRONG_ROLES or (USE_STRONG_MODEL and role in STRONG_ROLES):
        return GROQ_MODEL_STRONG
    return GROQ_MODEL
