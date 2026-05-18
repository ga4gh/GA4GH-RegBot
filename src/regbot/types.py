"""Shared typing helpers for RegBot (JSON shapes and chunk records)."""

from __future__ import annotations

from typing import Any, TypedDict


class ChunkRecord(TypedDict):
    id: str
    text: str
    metadata: dict[str, Any]


class RecommendationItem(TypedDict):
    """One actionable item; evidence must cite retrieved chunk ids only."""

    text: str
    evidence_chunk_ids: list[str]


class CitationItem(TypedDict, total=False):
    chunk_id: str
    reason: str


class GroundingAudit(TypedDict):
    ok: bool
    issues: list[str]
    allowed_chunk_count: int
    recommendation_count: int
    invalid_evidence_chunk_ids: list[str]
