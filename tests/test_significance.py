import pytest
from src.regbot.significance import (
    bootstrap_ci,
    holm_adjust,
    paired_bootstrap_ci,
    paired_permutation_p,
)


def test_bootstrap_ci_brackets_the_mean_and_is_deterministic():
    values = [0.0, 0.5, 1.0, 1.0, 0.25, 0.75, 1.0, 0.0]
    lo, hi = bootstrap_ci(values, resamples=2000, seed=1)
    mean = sum(values) / len(values)
    assert lo <= mean <= hi
    assert (lo, hi) == bootstrap_ci(values, resamples=2000, seed=1)


def test_bootstrap_ci_of_constant_is_degenerate():
    assert bootstrap_ci([0.5] * 10, resamples=500) == pytest.approx((0.5, 0.5))


def test_paired_bootstrap_rejects_unequal_lengths():
    with pytest.raises(ValueError):
        paired_bootstrap_ci([1.0], [1.0, 0.0])


def test_identical_systems_have_p_one():
    a = [0.1, 0.5, 0.9]
    assert paired_permutation_p(a, a) == 1.0


def test_exact_sign_flip_p_value_for_six_consistent_losses():
    # Six queries each lose 1.0 and the rest tie: only the two all-same-sign assignments
    # are as extreme as observed, so p = 2 / 2**6.
    system = [0.0] * 6 + [1.0] * 30
    baseline = [1.0] * 6 + [1.0] * 30
    assert paired_permutation_p(system, baseline) == pytest.approx(2 / 64)


def test_ties_do_not_dilute_the_test():
    base = [0.0, 0.0, 0.0]
    sys_ = [1.0, 1.0, 1.0]
    p_small = paired_permutation_p(sys_, base)
    p_padded = paired_permutation_p(sys_ + [0.5] * 50, base + [0.5] * 50)
    assert p_small == p_padded


def test_monte_carlo_branch_detects_a_large_consistent_effect():
    base = [0.0] * 40
    sys_ = [1.0] * 40
    assert paired_permutation_p(sys_, base, resamples=2000) < 0.01


def test_holm_is_monotone_and_capped():
    adj = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
    assert adj["a"] == pytest.approx(0.04)
    assert adj["c"] == pytest.approx(0.09)
    assert adj["b"] == pytest.approx(0.09)  # monotone: never below a smaller raw p's value
    assert adj["d"] == pytest.approx(0.5)
    assert all(v <= 1.0 for v in holm_adjust({"x": 0.6, "y": 0.7}).values())
