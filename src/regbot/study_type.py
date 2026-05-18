from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Lightweight keyword buckets for routing retrieval / prompts (not a clinical classifier).
_STUDY_KEYWORDS: List[Tuple[str, List[str]]] = [
    (
        "clinical_trial",
        [
            "clinical trial",
            "randomized",
            "randomised",
            "intervention",
            "phase i",
            "phase ii",
            "phase iii",
            "irb",
            "ethics committee",
        ],
    ),
    (
        "biobank",
        [
            "biobank",
            "biospecimen",
            "tissue bank",
            "sample repository",
            "specimen",
        ],
    ),
    (
        "cohort_study",
        [
            "cohort",
            "longitudinal",
            "prospective study",
            "registry",
            "population study",
        ],
    ),
    (
        "genomic_research",
        [
            "genome",
            "genomic",
            "whole genome",
            "wgs",
            "wes",
            "sequencing",
            "variant",
            "gwas",
        ],
    ),
]


def detect_study_type(text: str) -> str:
    if not text or not text.strip():
        return "unspecified"
    lowered = text.lower()
    scores: Dict[str, int] = {name: 0 for name, _ in _STUDY_KEYWORDS}
    for name, kws in _STUDY_KEYWORDS:
        for kw in kws:
            if kw in lowered:
                scores[name] += 1
    best = max(scores.values())
    if best == 0:
        # token-ish fallback
        if re.search(r"\b(gene|genetic|dna|rna)\b", lowered):
            return "genomic_research"
        return "unspecified"
    for name, _ in _STUDY_KEYWORDS:
        if scores[name] == best:
            return name
    return "unspecified"
