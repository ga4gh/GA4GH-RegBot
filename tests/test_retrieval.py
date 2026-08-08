"""
Retrieval ranking determinism.

Chroma's HNSW index is approximate: the same query embedding against the same collection
returned different tail neighbours across processes, which jittered the candidate-pool
boundary and propagated into the fused top-k. Benchmark numbers moved between identical
runs (recall@8 swung 0.841-0.855), which would make a `--min-recall` CI gate flaky.

These tests pin the two fixes: exact cosine ranking over in-memory embeddings, and
id-based tie-breaking in both dense ranking and reciprocal rank fusion. They stub the
embedding matrix directly, so no model download is needed in CI.
"""

import unittest

from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.retrieval import HybridRetriever
from src.regbot.types import provision_keys


def _retriever_with_embeddings(ids, vectors):
    r = HybridRetriever("unused")
    import numpy as np

    matrix = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    r._embeddings = matrix / norms
    r._embedding_ids = list(ids)
    return r


class TestDenseRanking(unittest.TestCase):
    def test_ranks_by_cosine_similarity(self) -> None:
        r = _retriever_with_embeddings(
            ["far", "near", "mid"],
            [[0.0, 1.0], [1.0, 0.0], [1.0, 1.0]],
        )
        self.assertEqual(r._dense_candidates([1.0, 0.0], 3), ["near", "mid", "far"])

    def test_limit_is_respected(self) -> None:
        r = _retriever_with_embeddings(["a", "b", "c"], [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
        self.assertEqual(len(r._dense_candidates([1.0, 0.0], 2)), 2)

    def test_ties_break_on_chunk_id_not_insertion_order(self) -> None:
        # Same vector under three ids inserted in non-alphabetical order.
        r = _retriever_with_embeddings(
            ["zebra", "apple", "mango"],
            [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
        )
        self.assertEqual(r._dense_candidates([1.0, 0.0], 3), ["apple", "mango", "zebra"])

    def test_repeated_calls_are_identical(self) -> None:
        r = _retriever_with_embeddings(
            [f"c{i}" for i in range(20)],
            [[1.0, i / 20.0] for i in range(20)],
        )
        runs = {tuple(r._dense_candidates([1.0, 0.3], 8)) for _ in range(10)}
        self.assertEqual(len(runs), 1)

    def test_unnormalized_query_is_handled(self) -> None:
        r = _retriever_with_embeddings(["a", "b"], [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(r._dense_candidates([5.0, 0.0], 1), ["a"])

    def test_no_embeddings_and_no_collection_returns_empty(self) -> None:
        r = HybridRetriever("unused")
        self.assertEqual(r._dense_candidates([1.0, 0.0], 5), [])


class TestProvisionCap(unittest.TestCase):
    """A result list should name distinct applicable rules, not repeat one of them."""

    def _chunk(self, cid, doc, section):
        return {"id": cid, "text": "x", "metadata": {"document_id": doc, "section": section}}

    def test_provision_keys_group_fragments_of_one_article(self) -> None:
        a = self._chunk("c1", "gdpr", "Article 35 — DPIA")
        b = self._chunk("c2", "gdpr", "Article 35 — DPIA")
        self.assertEqual(provision_keys(a), provision_keys(b))

    def test_fragments_of_different_articles_do_not_collide(self) -> None:
        a = self._chunk("c1", "gdpr", "Article 35 — DPIA")
        b = self._chunk("c2", "gdpr", "Article 36 — Prior consultation")
        self.assertNotEqual(provision_keys(a), provision_keys(b))

    def test_cap_admits_at_most_n_fragments_per_provision(self) -> None:
        # Simulates the selection loop: three fragments of one article, cap of two.
        fragments = [self._chunk(f"c{i}", "gdpr", "Article 35 — DPIA") for i in range(3)]
        cap, used, kept = 2, {}, []
        for chunk in fragments:
            keys = provision_keys(chunk)
            if any(used.get(k, 0) >= cap for k in keys):
                continue
            for k in keys:
                used[k] = used.get(k, 0) + 1
            kept.append(chunk)
        self.assertEqual(len(kept), 2)


class TestFusionDeterminism(unittest.TestCase):
    def test_fusion_is_order_independent_for_tied_scores(self) -> None:
        # Same two ranked lists, different iteration order of the inputs.
        a = reciprocal_rank_fusion([["x", "y"], ["y", "x"]], top_n=2)
        b = reciprocal_rank_fusion([["y", "x"], ["x", "y"]], top_n=2)
        self.assertEqual(a, b)

    def test_higher_fused_score_still_wins_over_tie_break(self) -> None:
        # 'zzz' appears first in both lists, so it must outrank 'aaa' despite the id order.
        self.assertEqual(
            reciprocal_rank_fusion([["zzz", "aaa"], ["zzz", "aaa"]], top_n=2),
            ["zzz", "aaa"],
        )

    def test_repeated_fusion_is_stable(self) -> None:
        lists = [["b", "c", "a"], ["a", "b", "c"]]
        runs = {tuple(reciprocal_rank_fusion(lists, top_n=3)) for _ in range(10)}
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
