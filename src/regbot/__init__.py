"""GA4GH RegBot: ingestion, hybrid retrieval, and compliance helpers (default LLM: local Ollama)."""

from src.regbot.config import DEFAULT_COLLECTION, DEFAULT_EMBEDDING_MODEL, MIN_TOKEN_OVERLAP
from src.regbot.types import ChunkRecord, GroundingAudit, RecommendationItem

__all__ = [
    "DEFAULT_COLLECTION",
    "DEFAULT_EMBEDDING_MODEL",
    "MIN_TOKEN_OVERLAP",
    "ChunkRecord",
    "GroundingAudit",
    "RecommendationItem",
]
