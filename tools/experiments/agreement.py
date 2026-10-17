"""
Inter-annotator agreement between two exported crosswalk label files.

    python tools/experiments/agreement.py labels_a.json labels_b.json

Candidates are matched on (cell, unit) and compared only where both annotators gave a
label. Reports Cohen's kappa on the 3-way labels and on binarised labels (2 vs. other — the
cut that defines the gold standard), the confusion matrix, and agreement on empty cells.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Dict, Hashable, List, Optional, Sequence, Tuple


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    if len(a) != len(b):
        raise ValueError("label sequences must align")
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def _labels(path: str) -> Tuple[Dict[Tuple[str, str], int], Dict[str, bool]]:
    with open(path, encoding="utf-8") as f:
        pool = json.load(f)
    out: Dict[Tuple[str, str], int] = {}
    empty: Dict[str, bool] = {}
    for q in pool.get("queries") or []:
        empty[q["query_id"]] = bool(q.get("empty_cell"))
        for c in q.get("candidates") or []:
            if c.get("label") is not None:
                out[(q["query_id"], c["provision"])] = int(c["label"])
    return out, empty


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("a")
    ap.add_argument("b")
    args = ap.parse_args(argv)
    la, ea = _labels(args.a)
    lb, eb = _labels(args.b)
    shared = sorted(set(la) & set(lb))
    if not shared:
        print("no candidates judged by both annotators")
        return 1
    x: List[int] = [la[k] for k in shared]
    y: List[int] = [lb[k] for k in shared]
    cells = sorted({k[0] for k in shared})
    print(f"{len(shared)} shared judgments across {len(cells)} cells")
    print(f"kappa (0/1/2):     {cohen_kappa(x, y):.3f}")
    print(f"kappa (2 vs other): {cohen_kappa([v == 2 for v in x], [v == 2 for v in y]):.3f}")
    print("confusion (rows = A, cols = B):")
    conf = Counter(zip(x, y))
    print("      " + "  ".join(f"B={j}" for j in (0, 1, 2)))
    for i in (0, 1, 2):
        print(f"A={i}  " + "  ".join(f"{conf[(i, j)]:>3}" for j in (0, 1, 2)))
    both = [c for c in cells if c in ea and c in eb]
    agree = sum(1 for c in both if ea[c] == eb[c])
    print(f"empty-cell agreement: {agree}/{len(both)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
