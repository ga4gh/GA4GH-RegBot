from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence


def reciprocal_rank_fusion(
    ranked_id_lists: Sequence[Sequence[str]],
    k: int = 60,
    top_n: int = 12,
) -> List[str]:
    scores: Dict[str, float] = defaultdict(float)
    for ids in ranked_id_lists:
        for rank, cid in enumerate(ids):
            scores[cid] += 1.0 / (k + rank + 1)
    # Tie-break on chunk id: without it, equal-scoring chunks order by dict insertion,
    # which makes the fused ranking depend on upstream pool ordering rather than score.
    ordered = sorted(scores.keys(), key=lambda x: (-scores[x], x))
    return ordered[:top_n]
