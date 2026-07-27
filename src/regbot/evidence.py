"""
Phase 3 evidence enrichment and human-review escalation (see docs/DESIGN.md §3.2).

Turns a flat ``evidence_chunk_ids`` list into reviewable ``evidence[]`` entries carrying
source, page, jurisdiction, a verbatim quote, and a governance pointer.

Two deliberate constraints, both following from the citation-grounding contract (§3.3):

* ``quote`` is a **verbatim span copied from the chunk**, never model-generated text. It is
  selected by token overlap with the recommendation, so a reviewer can see the actual
  clause without opening the source document.
* ``relevance`` is a **mechanical statement of the lexical link** ("shares terms: consent,
  withdrawal"), not an interpretive rationale. An LLM-authored rationale would be a fresh
  ungrounded claim sitting inside the evidence block that exists to prevent exactly that.

``governance_hint`` is informational routing only — it never asserts that a body has
approved anything, and RegBot issues no compliance decisions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from src.regbot.jurisdiction import chunk_jurisdiction_tags
from src.regbot.text_utils import tokenize

MAX_QUOTE_CHARS = 320

# Informational pointers to the human bodies that normally review each scope.
# Not legal advice, and not a claim that any body has been consulted.
_GOVERNANCE_HINTS: Dict[str, str] = {
    "SG": "Institutional Review Board under the HBRA; institutional data protection officer (PDPA)",
    "CN": "Human Genetic Resources administrative approval; institutional ethics committee",
    "TW": "Biobank ethics committee (Human Biobank Management Act); institutional data protection contact",
    "KR": "IRB under the Bioethics and Safety Act; privacy officer (PIPA)",
    "JP": "Research ethics review committee (MHLW guidelines); personal information handling officer (APPI)",
    "HK": "Institutional privacy officer (PDPO); research ethics committee",
    "EU": "Data Protection Officer (GDPR Art. 37); research ethics committee",
    "GA4GH": "Data Access Committee (DAC); institutional REC/IRB",
    "INTL": "Data Access Committee (DAC); institutional REC/IRB",
}

_FRAMEWORK_HINTS: Dict[str, str] = {
    "GDPR": "Data Protection Officer (GDPR Art. 37)",
    "REWS": "GA4GH REWS guidance; institutional REC/IRB",
}

# Tokens too common in policy prose to signal a real lexical link.
_STOPWORDS: Set[str] = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "by",
    "is",
    "are",
    "be",
    "as",
    "that",
    "this",
    "it",
    "at",
    "from",
    "should",
    "must",
    "may",
    "can",
    "will",
    "any",
    "all",
    "not",
    "if",
    "when",
    "where",
    "which",
    "their",
    "its",
    "such",
    "these",
    "data",
    "use",
    "used",
    "using",
}


def _normalize_ws(text: str) -> str:
    return " ".join(str(text or "").split())


def split_sentences(text: str) -> List[str]:
    """Split normalized chunk text into candidate spans for quoting."""
    normalized = _normalize_ws(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.;:!?])\s+|\s+•\s*|\s+-\s+", normalized)
    return [p.strip() for p in parts if p and p.strip()]


def select_quote(
    recommendation_text: str,
    chunk_text: str,
    *,
    max_chars: int = MAX_QUOTE_CHARS,
) -> str:
    """
    Pick the span of ``chunk_text`` most lexically supportive of the recommendation.

    Returns verbatim text (whitespace-normalized only). Falls back to the chunk's opening
    span when nothing overlaps, so evidence is never silently empty.
    """
    rec_tokens = set(tokenize(recommendation_text)) - _STOPWORDS
    sentences = split_sentences(chunk_text)
    if not sentences:
        return ""

    best = ""
    best_score = -1.0
    for sent in sentences:
        sent_tokens = set(tokenize(sent)) - _STOPWORDS
        if not sent_tokens:
            continue
        shared = len(rec_tokens & sent_tokens)
        # Favour spans that share vocabulary without rewarding sheer length.
        score = shared / (len(sent_tokens) ** 0.5)
        if score > best_score:
            best_score = score
            best = sent

    if best_score <= 0:
        best = sentences[0]

    if len(best) > max_chars:
        best = best[: max_chars - 1].rstrip() + "…"
    return best


def shared_terms(recommendation_text: str, chunk_text: str, *, limit: int = 6) -> List[str]:
    """Content words appearing in both texts, longest first (longer terms are more specific)."""
    rec_tokens = {t for t in tokenize(recommendation_text) if len(t) > 3} - _STOPWORDS
    chunk_tokens = {t for t in tokenize(chunk_text) if len(t) > 3} - _STOPWORDS
    shared = sorted(rec_tokens & chunk_tokens, key=lambda t: (-len(t), t))
    return shared[:limit]


def describe_relevance(recommendation_text: str, chunk_text: str) -> str:
    """Mechanical description of the lexical link — never an interpretive claim."""
    terms = shared_terms(recommendation_text, chunk_text)
    if not terms:
        return (
            "Cited as retrieved policy context; no shared terminology detected — verify manually."
        )
    return "Shares terminology with the recommendation: " + ", ".join(terms) + "."


def governance_hint(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """Informational pointer to the governance body that normally reviews this scope."""
    if not metadata:
        return None
    for code in sorted(chunk_jurisdiction_tags(metadata)):
        hint = _GOVERNANCE_HINTS.get(code)
        if hint:
            return hint
    framework = str(metadata.get("framework") or "").strip().upper()
    return _FRAMEWORK_HINTS.get(framework)


def build_evidence(
    recommendation_text: str,
    evidence_chunk_ids: Sequence[str],
    chunks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Expand cited chunk ids into reviewable evidence entries (DESIGN §3.2 Phase 3)."""
    by_id = {str(c["id"]): c for c in chunks if c.get("id")}
    out: List[Dict[str, Any]] = []

    for cid in evidence_chunk_ids:
        chunk = by_id.get(str(cid))
        if chunk is None:
            # Ungrounded id: the allow-list audit reports it; keep a marker so the
            # evidence list never silently disagrees with evidence_chunk_ids.
            out.append({"chunk_id": str(cid), "resolved": False})
            continue

        meta = dict(chunk.get("metadata") or {})
        text = str(chunk.get("text") or "")
        entry: Dict[str, Any] = {
            "chunk_id": str(cid),
            "resolved": True,
            "source": meta.get("source"),
            "page": meta.get("page"),
            "quote": select_quote(recommendation_text, text),
            "relevance": describe_relevance(recommendation_text, text),
        }
        if meta.get("document_id"):
            entry["document_id"] = meta["document_id"]
        tags = sorted(chunk_jurisdiction_tags(meta))
        if tags:
            entry["jurisdiction"] = tags[0] if len(tags) == 1 else tags
        if meta.get("framework"):
            entry["framework"] = meta["framework"]
        hint = governance_hint(meta)
        if hint:
            entry["governance_hint"] = hint
        out.append(entry)

    return out


def enrich_recommendations(
    recommendations: Sequence[Dict[str, Any]],
    chunks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Attach ``evidence[]`` to each recommendation, preserving existing keys."""
    enriched: List[Dict[str, Any]] = []
    for rec in recommendations:
        row = dict(rec)
        row["evidence"] = build_evidence(
            str(rec.get("text") or ""),
            [str(x) for x in (rec.get("evidence_chunk_ids") or [])],
            chunks,
        )
        enriched.append(row)
    return enriched


def assess_human_review(
    report: Dict[str, Any],
    chunks: Sequence[Dict[str, Any]],
    *,
    min_chunks: int = 1,
) -> Dict[str, Any]:
    """
    Decide whether the report must escalate to a human reviewer (DESIGN §3.2).

    Fail-safe by design: when retrieval is thin, grounding failed, or the overlap filter
    removed everything, the report says so rather than presenting weak output as an answer.
    ``review_reason`` uses the vocabulary fixed in DESIGN: ``weak_retrieval``,
    ``low_overlap``, ``grounding_failed``.
    """
    grounding = report.get("grounding") or {}
    overlap = grounding.get("overlap") or {}
    recommendations = report.get("recommendations") or []

    reasons: List[str] = []
    details: List[str] = []

    if len(chunks) < max(1, min_chunks):
        reasons.append("weak_retrieval")
        details.append(
            f"Retrieval returned {len(chunks)} chunk(s); "
            "there is not enough policy context to support a navigation report."
        )

    if not grounding.get("ok", True):
        reasons.append("grounding_failed")
        issues = grounding.get("issues") or []
        first = str(issues[0]) if issues else "citation grounding checks did not pass"
        details.append(f"Grounding audit failed: {first}")

    if overlap.get("dropped_all") and not overlap.get("skipped"):
        reasons.append("low_overlap")
        details.append(
            "Every recommendation fell below the token-overlap threshold "
            f"({overlap.get('min_threshold')}) against its cited chunks."
        )
    elif chunks and not recommendations:
        reasons.append("low_overlap")
        details.append("No recommendation survived grounding and overlap filtering.")

    if not reasons:
        return {"needs_human_review": False}

    # Order matters: weak retrieval explains the others when several fire at once.
    priority = ["weak_retrieval", "grounding_failed", "low_overlap"]
    primary = next(r for r in priority if r in reasons)

    return {
        "needs_human_review": True,
        "review_reason": primary,
        "review_reasons": sorted(set(reasons), key=priority.index),
        "review_details": " ".join(details),
    }


def apply_phase3_enrichment(
    report: Dict[str, Any],
    chunks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach evidence[] and human-review flags to a finished report, in place."""
    if report.get("recommendations"):
        report["recommendations"] = enrich_recommendations(report["recommendations"], chunks)
    report.update(assess_human_review(report, chunks))
    return report
