"""Jurisdiction vocabulary and metadata helpers (see docs/DESIGN.md §3.1)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Normalized codes for REWS regional scope + framework docs.
JURISDICTION_CODES: Tuple[str, ...] = (
    "SG",
    "CN",
    "TW",
    "KR",
    "JP",
    "HK",
    "EU",
    "GA4GH",
    "INTL",
)

# Short labels for UI (corpus scope hints — not legal advice).
JURISDICTION_LABELS: Dict[str, str] = {
    "SG": "Singapore — PDPA, HBRA, Health Information Bill",
    "CN": "China — HGR, PIPL, Data Security Law",
    "TW": "Taiwan — Human Biobank Act, PDPA",
    "KR": "Korea — Bioethics Act, PIPA",
    "JP": "Japan — Ethical Guidelines, APPI, Genomic Medicine Act",
    "HK": "Hong Kong — PDPO, cross-border transfer (s.33)",
    "EU": "EU — GDPR and related briefs",
    "GA4GH": "GA4GH / REWS framework (international norms)",
    "INTL": "Cross-cutting GA4GH guidance",
}


def normalize_jurisdiction(code: str) -> str:
    return code.strip().upper()


def jurisdiction_option_label(code: str) -> str:
    c = normalize_jurisdiction(code)
    label = JURISDICTION_LABELS.get(c, c)
    return f"{c} — {label}" if c in JURISDICTION_LABELS else c


def jurisdiction_options_for_ui() -> List[Tuple[str, str]]:
    """Return (code, display_label) pairs for select widgets."""
    return [(c, jurisdiction_option_label(c)) for c in JURISDICTION_CODES]


def parse_jurisdiction_filter(
    selected: Optional[Iterable[str]],
) -> Optional[List[str]]:
    """Normalize UI/CLI selection; None or empty means no filter."""
    if not selected:
        return None
    out: List[str] = []
    seen: Set[str] = set()
    for raw in selected:
        if not raw or not str(raw).strip():
            continue
        code = normalize_jurisdiction(str(raw))
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out or None


def chunk_jurisdiction_tags(metadata: Optional[Dict[str, Any]]) -> Set[str]:
    if not metadata:
        return set()
    raw = metadata.get("jurisdiction")
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {normalize_jurisdiction(str(x)) for x in raw if str(x).strip()}
    return {normalize_jurisdiction(str(raw))}


def jurisdiction_matches(
    metadata: Optional[Dict[str, Any]],
    selected: Optional[Iterable[str]],
) -> bool:
    """True if no filter, or chunk jurisdiction overlaps selected codes."""
    codes = parse_jurisdiction_filter(selected)
    if codes is None:
        return True
    tags = chunk_jurisdiction_tags(metadata)
    if not tags:
        return False
    want = {normalize_jurisdiction(c) for c in codes}
    return bool(tags & want)


def jurisdictions_in_manifest(chunks: List[Dict[str, Any]]) -> List[str]:
    """Distinct jurisdiction codes present in stored chunks."""
    found: Set[str] = set()
    for rec in chunks:
        found |= chunk_jurisdiction_tags(rec.get("metadata"))
    return sorted(found)
