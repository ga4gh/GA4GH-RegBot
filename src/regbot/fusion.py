from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence

from src.regbot.config import FUSION_STRATEGY


def reciprocal_rank_fusion(
    ranked_id_lists: Sequence[Sequence[str]],
    k: int = 60,
    top_n: int = 12,
    strategy: str = "",
) -> List[str]:
    """
    Fuse ranked lists by reciprocal rank.

    ``strategy`` selects how a chunk's per-channel contributions combine:

    ``max`` (default)
        Take the single best channel. A chunk that ranks #2 in BM25 outranks one that is
        merely respectable in both channels.
    ``sum``
        Classic RRF — add every channel's contribution.

    **Why max is the default.** Additive RRF rewards agreement between channels, which is
    the right instinct for web search but the wrong one for statute retrieval: the
    operative clause is frequently a precise lexical hit that a 384-dimension
    general-purpose embedding ranks poorly. Measured on the gold set, the GA4GH
    prohibition on re-identification sat at BM25 #2 and dense #50, and additive fusion let
    six chunks of general privacy prose — mediocre in both channels — beat it out of the
    top-8 entirely.

    The trade is real and runs the same direction as the lexical-weighted pool sizes:
    ``max`` gains recall and precision, and gives up rank-1 accuracy and MRR, because it
    stops requiring corroboration. Recall is the primary metric here — the report feeds a
    reviewer who reads the whole list. Set ``REGBOT_FUSION=sum`` to restore classic RRF.
    See docs/eval_results.md §4c.
    """
    mode = (strategy or FUSION_STRATEGY).strip().lower()
    contributions: Dict[str, List[float]] = defaultdict(list)
    for ids in ranked_id_lists:
        for rank, cid in enumerate(ids):
            contributions[cid].append(1.0 / (k + rank + 1))

    combine = max if mode == "max" else sum
    scores = {cid: combine(vals) for cid, vals in contributions.items()}

    # Tie-break on chunk id: without it, equal-scoring chunks order by dict insertion,
    # which makes the fused ranking depend on upstream pool ordering rather than score.
    ordered = sorted(scores.keys(), key=lambda x: (-scores[x], x))
    return ordered[:top_n]
