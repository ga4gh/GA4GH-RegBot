"""
Judgment units for relevance labelling and scoring.

``provision_keys`` (src/regbot/types.py) identifies a chunk by document + section. For a
document whose structure was never detected — no section headings, no pages — every chunk
maps to the same key, so the whole document becomes one "provision": finding any of its
161 chunks would count as finding the rule. That inflates provision recall and, when pooling,
collapses distinct passages of that document into a single candidate.

A document is *coarse* when it averages at least ``ratio`` chunks per provision key. For
coarse documents the unit is the chunk itself; everywhere else it is the provision. The rule
is mechanical and reported with the results, so a reader can see which documents were
scored at which granularity.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Set

from src.regbot.types import provision_keys

COARSE_RATIO = 5.0


def coarse_documents(chunks: Iterable[Dict[str, Any]], ratio: float = COARSE_RATIO) -> Set[str]:
    counts: Dict[str, int] = defaultdict(int)
    keys: Dict[str, Set[str]] = defaultdict(set)
    for c in chunks:
        doc = str((c.get("metadata") or {}).get("document_id"))
        counts[doc] += 1
        keys[doc] |= provision_keys(c)
    return {d for d, n in counts.items() if keys[d] and n / len(keys[d]) >= ratio}


def judgment_units(chunk: Dict[str, Any], coarse: Set[str]) -> Set[str]:
    doc = str((chunk.get("metadata") or {}).get("document_id"))
    if doc in coarse:
        return {f"{doc} #chunk {chunk['id']}"}
    return provision_keys(chunk)
