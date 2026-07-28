import os
from typing import Any

DEFAULT_COLLECTION = "regbot_policy"
# Minimum fraction of recommendation tokens that must appear in at least one cited chunk
# (token recall). Set to 0.0 to disable overlap filtering for the LLM path.
MIN_TOKEN_OVERLAP = float(os.getenv("REGBOT_MIN_TOKEN_OVERLAP", "0.06"))
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "REGBOT_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
DEFAULT_LLM_MODEL = os.getenv("REGBOT_LLM_MODEL", "gpt-4o-mini")
CHROMA_SUBDIR = "chroma"
MANIFEST_NAME = "manifest.json"


def _pos_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# Candidate pool sizes feeding reciprocal rank fusion. Defaults are the Phase 2 tuned
# values (see docs/eval_results.md): weighting the lexical pool higher than the dense pool
# improves recall on legal text, where rare statutory terms carry most of the signal.
SEMANTIC_CANDIDATES = _pos_int_env("REGBOT_SEMANTIC_CANDIDATES", 12)
BM25_CANDIDATES = _pos_int_env("REGBOT_BM25_CANDIDATES", 48)


def _fusion_strategy() -> str:
    """How reciprocal-rank contributions combine: 'max' (default) or 'sum' (classic RRF)."""
    v = os.getenv("REGBOT_FUSION", "max").strip().lower()
    return "sum" if v == "sum" else "max"


FUSION_STRATEGY = _fusion_strategy()


def llm_provider() -> str:
    """ollama (default): local Llama / Mistral via Ollama. Set REGBOT_LLM_PROVIDER=openai for OpenAI API."""
    v = os.getenv("REGBOT_LLM_PROVIDER", "ollama").strip().lower()
    if v in ("openai", "azure_openai"):
        return "openai"
    return "ollama"


def ollama_openai_base_url() -> str:
    """Ollama exposes OpenAI-compatible routes under .../v1 (e.g. http://127.0.0.1:11434/v1)."""
    base = os.getenv("REGBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


# Dummy key for Ollama's OpenAI shim (ignored by Ollama).
OLLAMA_API_KEY = os.getenv("REGBOT_OLLAMA_API_KEY", "ollama")
DEFAULT_OLLAMA_MODEL = os.getenv("REGBOT_OLLAMA_MODEL", "llama3")


def _nonneg_int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# Retries for transient errors on the OpenAI Python client (OpenAI API or Ollama-compatible URL).
OPENAI_MAX_RETRIES = _nonneg_int_env("REGBOT_OPENAI_MAX_RETRIES", 3)


def chromadb_settings() -> Any:
    """Chroma PersistentClient settings. Telemetry defaults off unless REGBOT_CHROMA_ANONYMIZED_TELEMETRY=1."""
    from chromadb.config import Settings

    raw = os.getenv("REGBOT_CHROMA_ANONYMIZED_TELEMETRY", "0").strip().lower()
    telemetry_on = raw in ("1", "true", "yes", "on")
    return Settings(anonymized_telemetry=telemetry_on)
