"""Shared typing helpers and chunk identity for RegBot."""

from __future__ import annotations

from typing import Any, Set, TypedDict


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


def provision_keys(chunk: dict[str, Any]) -> Set[str]:
    """
    Identify the *provision(s)* a chunk belongs to — the rule, not the fragment.

    Chunk identity is unstable under re-chunking, so anything reasoning about "did we find
    this rule" must key on the provision instead. Keyed on ``document_id`` plus ``section``
    where the source is line-structured, falling back to page and then to the document
    alone. A chunk straddling two sections belongs to both.

    Lives here rather than in the evaluation module because retrieval uses it too, to cap
    how many fragments of one provision may occupy the result list.
    """
    meta = chunk.get("metadata") or {}
    doc = str(meta.get("document_id") or meta.get("source") or "?")
    section = str(meta.get("section") or "").strip()
    if section:
        return {f"{doc} § {part.strip()}" for part in section.split(";") if part.strip()}
    page = meta.get("page")
    if page not in (None, "", 0):
        return {f"{doc} p{page}"}
    return {doc}
