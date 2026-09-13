import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
HOSTED = os.getenv("VERCEL") == "1"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'evidence.db'}")
PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if HOSTED else "ollama").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = (
    os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    if PROVIDER == "gemini"
    else os.getenv("OLLAMA_MODEL", "gemma4:e4b")
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
REQUIRE_KEY = HOSTED or os.getenv("REQUIRE_ACCESS_KEY", "0") == "1"
ACCESS_KEY = os.getenv("APP_ACCESS_KEY", "") if REQUIRE_KEY else ""
TIMEOUT = min(
    60 if HOSTED else 120,
    max(5, float(os.getenv("MODEL_TIMEOUT_SECONDS", "60" if HOSTED else "120"))),
)
PROMPT_VERSION = "evidence-v1"
MAX_UPLOAD = 4 * 1024 * 1024


def validate_hosting():
    if REQUIRE_KEY and not ACCESS_KEY:
        raise RuntimeError("Configure APP_ACCESS_KEY before network hosting.")
    if HOSTED:
        if not DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Vercel requires a persistent PostgreSQL DATABASE_URL.")
        if PROVIDER != "gemini" or not GEMINI_API_KEY:
            raise RuntimeError("Configure Gemini and GEMINI_API_KEY for Vercel.")
