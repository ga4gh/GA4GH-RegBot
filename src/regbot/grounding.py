from __future__ import annotations

from typing import Any, Dict, List, Set

from src.regbot.text_utils import tokenize
from src.regbot.types import RecommendationItem


def allowed_chunk_ids(chunks: List[Dict[str, Any]]) -> Set[str]:
    return {str(c["id"]) for c in chunks if c.get("id")}


def normalize_recommendations(raw: Any) -> List[RecommendationItem]:
    """
    Normalize LLM or legacy output into structured recommendations.
    Legacy plain strings become items with empty evidence (will fail strict grounding).
    """
    if not isinstance(raw, list):
        return []
    out: List[RecommendationItem] = []
    for item in raw:
        if isinstance(item, str):
            rec: RecommendationItem = {
                "text": item.strip(),
                "evidence_chunk_ids": [],
            }
            out.append(rec)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("recommendation") or ""
            ids = item.get("evidence_chunk_ids") or item.get("chunk_ids") or []
            if not isinstance(ids, list):
                ids = []
            rec2: RecommendationItem = {
                "text": str(text).strip(),
                "evidence_chunk_ids": [str(x) for x in ids],
            }
            out.append(rec2)
    return out


def max_token_recall_against_chunks(rec_text: str, chunk_texts: List[str]) -> float:
    """
    Max over cited chunks of |T(rec) ∩ T(chunk)| / max(1, |T(rec)|).
    Measures whether the recommendation wording is supported by chunk vocabulary.
    """
    tr = set(tokenize(rec_text))
    if not tr:
        return 0.0
    best = 0.0
    for ct in chunk_texts:
        if not ct:
            continue
        tc = set(tokenize(ct))
        inter = len(tr & tc)
        best = max(best, inter / len(tr))
    return best


def filter_recommendations_by_token_overlap(
    recommendations: List[RecommendationItem],
    chunks: List[Dict[str, Any]],
    *,
    min_overlap: float,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Drop recommendations with no evidence ids, or whose token recall against cited
    chunk texts is below ``min_overlap``. Adds ``token_overlap_score`` to each kept row.
    Pass ``min_overlap <= 0`` to skip filtering (scores still attached when ids present).
    """
    id_to_text = {str(c["id"]): str(c.get("text") or "") for c in chunks if c.get("id")}
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []

    for rec in recommendations:
        text = str(rec.get("text") or "").strip()
        ids = list(rec.get("evidence_chunk_ids") or [])
        if not ids:
            dropped.append(
                {
                    "reason": "no_evidence_chunk_ids",
                    "text_preview": text[:120],
                    "score": 0.0,
                }
            )
            continue

        chunk_texts = [id_to_text.get(i, "") for i in ids if i in id_to_text]
        score = max_token_recall_against_chunks(text, chunk_texts)

        row: Dict[str, Any] = {
            "text": text,
            "evidence_chunk_ids": ids,
            "token_overlap_score": round(score, 4),
        }

        if min_overlap <= 0:
            kept.append(row)
            continue

        if score < min_overlap:
            dropped.append(
                {
                    "reason": "low_token_overlap",
                    "text_preview": text[:120],
                    "score": score,
                    "min_threshold": min_overlap,
                }
            )
            continue

        kept.append(row)

    meta: Dict[str, Any] = {
        "input_count": len(recommendations),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "dropped_all": len(recommendations) > 0 and len(kept) == 0,
        "min_threshold": min_overlap,
        "dropped": dropped[:20],
    }
    return kept, meta


def audit_report_grounding(
    report: Dict[str, Any],
    allowed_ids: Set[str],
    *,
    require_evidence_per_recommendation: bool = True,
    validate_supplementary_citations: bool = True,
) -> Dict[str, Any]:
    """
    Strong grounding: every structured recommendation must list at least one
    evidence_chunk_id from the retrieved allow-list. Optional top-level ``citations``
    entries are also checked if present.
    """
    raw_recs = report.get("recommendations")
    recs = normalize_recommendations(raw_recs)
    issues: List[str] = []
    invalid_evidence: List[str] = []

    if raw_recs and not recs:
        issues.append("Field 'recommendations' was present but could not be parsed.")

    for i, rec in enumerate(recs):
        text = rec.get("text", "")
        ids = list(rec.get("evidence_chunk_ids") or [])
        if not text:
            issues.append(f"recommendations[{i}] has empty text.")
        if require_evidence_per_recommendation and not ids:
            issues.append(f"recommendations[{i}] has empty evidence_chunk_ids.")
        for eid in ids:
            if eid not in allowed_ids:
                invalid_evidence.append(eid)

    if invalid_evidence:
        uniq = list(dict.fromkeys(invalid_evidence))
        issues.append(f"Invalid evidence_chunk_ids (not in retrieved set): {uniq}")

    if validate_supplementary_citations:
        citations = report.get("citations") or []
        for j, c in enumerate(citations):
            if not isinstance(c, dict):
                issues.append(f"citations[{j}] is not an object.")
                continue
            cid = c.get("chunk_id")
            if cid is not None and str(cid) not in allowed_ids:
                issues.append(f"citations[{j}] invalid chunk_id: {cid!r}")

    ok = len(issues) == 0
    return {
        "ok": ok,
        "issues": issues,
        "allowed_chunk_count": len(allowed_ids),
        "recommendation_count": len(recs),
        "invalid_evidence_chunk_ids": list(dict.fromkeys(invalid_evidence)),
    }


def audit_citation_grounding(
    report: Dict[str, Any],
    allowed_ids: Set[str],
    *,
    strict_min_citations_vs_recommendations: bool = True,
) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper: delegate to :func:`audit_report_grounding`.
    The ``strict_min_citations_vs_recommendations`` flag is ignored; strictness is
    expressed via structured recommendations + evidence_chunk_ids.
    """
    _ = strict_min_citations_vs_recommendations
    base = audit_report_grounding(
        report,
        allowed_ids,
        require_evidence_per_recommendation=True,
        validate_supplementary_citations=True,
    )
    # Preserve legacy keys some callers/tests may look for
    citations = report.get("citations") or []
    valid_ids: List[str] = []
    for c in citations:
        if isinstance(c, dict):
            cid = c.get("chunk_id")
            if cid is not None and str(cid) in allowed_ids:
                valid_ids.append(str(cid))
    out = dict(base)
    out["citation_count"] = len(citations)
    out["valid_citation_chunk_ids"] = valid_ids
    return out
