"""
Paired significance tests for per-query retrieval metrics.

With a few dozen queries, a 2-3 point difference in a macro-averaged metric is often one
provision moving in one query (docs/eval_results.md §3b). Before a configuration change is
reported as an improvement, compare it against the baseline *per query*:

``bootstrap_ci``        percentile CI for a mean, resampling queries with replacement
``paired_bootstrap_ci`` percentile CI for the mean per-query difference between two systems
``paired_permutation_p`` two-sided sign-flip permutation p-value for that difference
``holm_adjust``         Holm-Bonferroni step-down adjustment across several comparisons

All functions are deterministic for a given ``seed`` so reported intervals reproduce.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted sequence, ``q`` in [0, 1]."""
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def bootstrap_ci(
    values: Sequence[float],
    *,
    resamples: int = 10000,
    alpha: float = 0.05,
    seed: int = 13,
) -> Tuple[float, float]:
    """Percentile bootstrap CI for the mean of ``values``."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(_mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return (_percentile(means, alpha / 2), _percentile(means, 1 - alpha / 2))


def paired_bootstrap_ci(
    system: Sequence[float],
    baseline: Sequence[float],
    **kwargs: float,
) -> Tuple[float, float]:
    """CI for mean(system - baseline), resampling queries jointly."""
    if len(system) != len(baseline):
        raise ValueError("paired samples must have equal length")
    diffs = [s - b for s, b in zip(system, baseline)]
    return bootstrap_ci(diffs, **kwargs)  # type: ignore[arg-type]


def paired_permutation_p(
    system: Sequence[float],
    baseline: Sequence[float],
    *,
    resamples: int = 10000,
    seed: int = 13,
) -> float:
    """
    Two-sided paired permutation (sign-flip) test of mean(system - baseline) == 0.

    Under the null, each query's difference is equally likely to carry either sign. Queries
    with zero difference contribute nothing either way, which is why this test stays valid
    when most queries tie — the common case when two retrievers differ on a handful of
    queries. Exact enumeration is used when there are at most 16 non-zero differences.
    """
    if len(system) != len(baseline):
        raise ValueError("paired samples must have equal length")
    diffs = [s - b for s, b in zip(system, baseline) if abs(s - b) > 1e-12]
    if not diffs:
        return 1.0
    observed = abs(sum(diffs))
    tol = 1e-12
    if len(diffs) <= 16:
        total = 1 << len(diffs)
        extreme = 0
        for mask in range(total):
            s = sum(d if (mask >> i) & 1 else -d for i, d in enumerate(diffs))
            if abs(s) >= observed - tol:
                extreme += 1
        return extreme / total
    rng = random.Random(seed)
    extreme = 0
    for _ in range(resamples):
        s = sum(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(s) >= observed - tol:
            extreme += 1
    # +1 smoothing: the observed assignment is itself one permutation.
    return (extreme + 1) / (resamples + 1)


def holm_adjust(p_values: Dict[str, float]) -> Dict[str, float]:
    """Holm-Bonferroni adjusted p-values, monotone and capped at 1."""
    ordered: List[Tuple[str, float]] = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: Dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted
