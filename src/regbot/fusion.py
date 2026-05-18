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
    ordered = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return ordered[:top_n]
