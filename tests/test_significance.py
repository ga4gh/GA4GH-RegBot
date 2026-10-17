import unittest

from src.regbot.significance import (
    bootstrap_ci,
    holm_adjust,
    paired_bootstrap_ci,
    paired_permutation_p,
)


class SignificanceTests(unittest.TestCase):
    def test_bootstrap_ci_brackets_the_mean_and_is_deterministic(self):
        values = [0.0, 0.5, 1.0, 1.0, 0.25, 0.75, 1.0, 0.0]
        lo, hi = bootstrap_ci(values, resamples=2000, seed=1)
        mean = sum(values) / len(values)
        self.assertLessEqual(lo, mean)
        self.assertLessEqual(mean, hi)
        self.assertEqual((lo, hi), bootstrap_ci(values, resamples=2000, seed=1))

    def test_bootstrap_ci_of_constant_is_degenerate(self):
        lo, hi = bootstrap_ci([0.5] * 10, resamples=500)
        self.assertAlmostEqual(lo, 0.5)
        self.assertAlmostEqual(hi, 0.5)

    def test_paired_bootstrap_rejects_unequal_lengths(self):
        with self.assertRaises(ValueError):
            paired_bootstrap_ci([1.0], [1.0, 0.0])

    def test_identical_systems_have_p_one(self):
        a = [0.1, 0.5, 0.9]
        self.assertEqual(paired_permutation_p(a, a), 1.0)

    def test_exact_sign_flip_p_value_for_six_consistent_losses(self):
        # Six queries each lose 1.0 and the rest tie: only the two all-same-sign assignments
        # are as extreme as observed, so p = 2 / 2**6.
        system = [0.0] * 6 + [1.0] * 30
        baseline = [1.0] * 6 + [1.0] * 30
        self.assertAlmostEqual(paired_permutation_p(system, baseline), 2 / 64)

    def test_ties_do_not_dilute_the_test(self):
        base = [0.0, 0.0, 0.0]
        sys_ = [1.0, 1.0, 1.0]
        p_small = paired_permutation_p(sys_, base)
        p_padded = paired_permutation_p(sys_ + [0.5] * 50, base + [0.5] * 50)
        self.assertEqual(p_small, p_padded)

    def test_monte_carlo_branch_detects_a_large_consistent_effect(self):
        base = [0.0] * 40
        sys_ = [1.0] * 40
        self.assertLess(paired_permutation_p(sys_, base, resamples=2000), 0.01)

    def test_holm_is_monotone_and_capped(self):
        adj = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
        self.assertAlmostEqual(adj["a"], 0.04)
        self.assertAlmostEqual(adj["c"], 0.09)
        # Monotone: never below the adjusted value of a smaller raw p.
        self.assertAlmostEqual(adj["b"], 0.09)
        self.assertAlmostEqual(adj["d"], 0.5)
        self.assertTrue(all(v <= 1.0 for v in holm_adjust({"x": 0.6, "y": 0.7}).values()))


if __name__ == "__main__":
    unittest.main()
