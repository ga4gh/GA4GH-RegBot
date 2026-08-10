import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from src.regbot.evaluation import (
    chunk_matches_anchor,
    evaluate_gold_set,
    format_markdown_report,
    load_gold_set,
    provision_keys,
    resolve_anchors,
    score_provisions,
    score_ranking,
)

CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "doc_a_p1_c0",
        "text": "Participants may withdraw consent at any time without penalty.",
        "metadata": {"document_id": "doc-a", "source": "a.pdf", "page": 1},
    },
    {
        "id": "doc_a_p2_c1",
        "text": "Transfer limitation obligation applies to cross-border sharing.",
        "metadata": {"document_id": "doc-a", "source": "a.pdf", "page": 2},
    },
    {
        "id": "doc_b_p0_c0",
        "text": "A data protection impact assessment is required for high-risk processing.",
        "metadata": {"document_id": "doc-b", "source": "b.txt", "page": 0},
    },
]


class TestAnchorMatching(unittest.TestCase):
    def test_matches_on_document_and_phrase(self) -> None:
        anchor = {"document_id": "doc-a", "contains": "withdraw consent"}
        self.assertTrue(chunk_matches_anchor(CHUNKS[0], anchor))
        self.assertFalse(chunk_matches_anchor(CHUNKS[1], anchor))

    def test_phrase_match_is_case_and_whitespace_insensitive(self) -> None:
        anchor = {"document_id": "doc-a", "contains": "WITHDRAW   consent"}
        self.assertTrue(chunk_matches_anchor(CHUNKS[0], anchor))

    def test_page_constraint(self) -> None:
        self.assertTrue(chunk_matches_anchor(CHUNKS[1], {"document_id": "doc-a", "page": 2}))
        self.assertFalse(chunk_matches_anchor(CHUNKS[1], {"document_id": "doc-a", "page": 1}))

    def test_literal_chunk_id_escape_hatch(self) -> None:
        self.assertTrue(chunk_matches_anchor(CHUNKS[2], {"chunk_id": "doc_b_p0_c0"}))
        self.assertFalse(chunk_matches_anchor(CHUNKS[2], {"chunk_id": "nope"}))

    def test_resolve_reports_unresolved_instead_of_dropping(self) -> None:
        anchors = [
            {"document_id": "doc-a", "contains": "withdraw consent"},
            {"document_id": "doc-a", "contains": "phrase that does not exist"},
        ]
        ids, unresolved = resolve_anchors(anchors, CHUNKS)
        self.assertEqual(ids, {"doc_a_p1_c0"})
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["contains"], "phrase that does not exist")


class TestMetrics(unittest.TestCase):
    def test_perfect_ranking(self) -> None:
        scores = score_ranking(["a", "b", "c"], {"a", "b"}, ks=[1, 2, 3])
        self.assertEqual(scores["recall@2"], 1.0)
        self.assertEqual(scores["precision@2"], 1.0)
        self.assertEqual(scores["mrr@1"], 1.0)
        self.assertEqual(scores["hit@1"], 1.0)

    def test_recall_and_precision_split(self) -> None:
        # gold = {a, z}; only 'a' retrieved in top-3 of 3 results
        scores = score_ranking(["x", "a", "y"], {"a", "z"}, ks=[3])
        self.assertEqual(scores["recall@3"], 0.5)
        self.assertAlmostEqual(scores["precision@3"], 1 / 3, places=4)
        self.assertEqual(scores["mrr@3"], 0.5)

    def test_no_relevant_in_top_k(self) -> None:
        scores = score_ranking(["x", "y"], {"a"}, ks=[2])
        self.assertEqual(scores["recall@2"], 0.0)
        self.assertEqual(scores["mrr@2"], 0.0)
        self.assertEqual(scores["hit@2"], 0.0)

    def test_precision_uses_returned_count_not_k(self) -> None:
        # Report both conventions: returned-count precision and fixed-k precision.
        scores = score_ranking(["a"], {"a"}, ks=[5])
        self.assertEqual(scores["precision@5"], 1.0)
        self.assertEqual(scores["precision_fixed@5"], 0.2)

    def test_empty_ranking_is_zero_not_error(self) -> None:
        scores = score_ranking([], {"a"}, ks=[3])
        self.assertEqual(scores["recall@3"], 0.0)
        self.assertEqual(scores["precision@3"], 0.0)


def _stub_retriever(ranking: List[str]):
    def fn(query: str, top_k: int, jurisdiction: Optional[List[str]]) -> List[Dict[str, Any]]:
        by_id = {c["id"]: c for c in CHUNKS}
        return [by_id[i] for i in ranking[:top_k] if i in by_id]

    return fn


class TestProvisionRecall(unittest.TestCase):
    """Provision-level recall must stay stable when the chunker changes."""

    def _chunk(self, cid, doc, section=None, page=0):
        meta = {"document_id": doc, "page": page}
        if section:
            meta["section"] = section
        return {"id": cid, "text": "x", "metadata": meta}

    def test_key_uses_document_and_section(self) -> None:
        c = self._chunk("a", "gdpr-full-text", "Article 35 — DPIA")
        self.assertEqual(provision_keys(c), {"gdpr-full-text § Article 35 — DPIA"})

    def test_chunk_spanning_two_sections_belongs_to_both(self) -> None:
        c = self._chunk(
            "a", "gdpr-full-text", "Article 8 — Child consent; Article 9 — Special categories"
        )
        self.assertEqual(len(provision_keys(c)), 2)

    def test_falls_back_to_page_then_document(self) -> None:
        self.assertEqual(provision_keys(self._chunk("a", "frs", page=5)), {"frs p5"})
        self.assertEqual(provision_keys(self._chunk("a", "frs", page=0)), {"frs"})

    def test_two_chunks_of_one_article_count_once(self) -> None:
        # The core property: splitting a provision into more chunks must not change recall.
        gold_one = [self._chunk("g1", "law", "Article 8")]
        gold_two = [self._chunk("g1", "law", "Article 8"), self._chunk("g2", "law", "Article 8")]
        retrieved = [self._chunk("r1", "law", "Article 8")]
        self.assertEqual(
            score_provisions(retrieved, gold_one, [1])["provision_recall@1"],
            score_provisions(retrieved, gold_two, [1])["provision_recall@1"],
        )

    def test_retrieving_a_different_fragment_of_the_right_article_counts(self) -> None:
        gold = [self._chunk("g1", "law", "Article 8")]
        other_fragment = [self._chunk("r9", "law", "Article 8")]
        self.assertEqual(score_provisions(other_fragment, gold, [1])["provision_recall@1"], 1.0)

    def test_wrong_article_scores_zero(self) -> None:
        gold = [self._chunk("g1", "law", "Article 8")]
        wrong = [self._chunk("r1", "law", "Article 14")]
        self.assertEqual(score_provisions(wrong, gold, [1])["provision_recall@1"], 0.0)

    def test_partial_coverage(self) -> None:
        gold = [self._chunk("g1", "law", "Article 8"), self._chunk("g2", "law", "Article 9")]
        got = [self._chunk("r1", "law", "Article 8")]
        self.assertEqual(score_provisions(got, gold, [1])["provision_recall@1"], 0.5)

    def test_empty_gold_is_zero_not_error(self) -> None:
        self.assertEqual(score_provisions([], [], [1])["provision_recall@1"], 0.0)


class TestEvaluateGoldSet(unittest.TestCase):
    def test_scores_a_resolvable_query(self) -> None:
        gold = {
            "version": "test",
            "queries": [
                {
                    "query_id": "q1",
                    "query": "withdrawal",
                    "relevant": [{"document_id": "doc-a", "contains": "withdraw consent"}],
                }
            ],
        }
        result = evaluate_gold_set(
            gold, CHUNKS, _stub_retriever(["doc_a_p1_c0", "doc_b_p0_c0"]), ks=[1, 2]
        )
        self.assertEqual(result["query_count"], 1)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(result["aggregate"]["recall@1"], 1.0)

    def test_query_with_unresolvable_anchors_is_skipped_not_scored(self) -> None:
        gold = {
            "queries": [
                {
                    "query_id": "stale",
                    "query": "anything",
                    "relevant": [{"document_id": "doc-missing", "contains": "gone"}],
                }
            ]
        }
        result = evaluate_gold_set(gold, CHUNKS, _stub_retriever(["doc_a_p1_c0"]))
        self.assertEqual(result["query_count"], 0)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["skipped"][0]["reason"], "no_gold_anchor_resolved")

    def test_jurisdiction_is_passed_to_retriever(self) -> None:
        seen: List[Optional[List[str]]] = []

        def fn(query: str, top_k: int, jurisdiction: Optional[List[str]]) -> List[Dict[str, Any]]:
            seen.append(jurisdiction)
            return [CHUNKS[0]]

        gold = {
            "queries": [
                {
                    "query_id": "q",
                    "query": "x",
                    "jurisdiction": "SG",
                    "relevant": [{"document_id": "doc-a", "contains": "withdraw consent"}],
                }
            ]
        }
        evaluate_gold_set(gold, CHUNKS, fn)
        self.assertEqual(seen, [["SG"]])

    def test_markdown_report_renders(self) -> None:
        gold = {
            "queries": [
                {
                    "query_id": "q1",
                    "query": "withdrawal",
                    "relevant": [{"document_id": "doc-a", "contains": "withdraw consent"}],
                }
            ]
        }
        result = evaluate_gold_set(gold, CHUNKS, _stub_retriever(["doc_a_p1_c0"]), ks=[1])
        md = format_markdown_report(result)
        self.assertIn("Recall@k", md)
        self.assertIn("q1", md)


class TestLoadGoldSet(unittest.TestCase):
    def _write(self, body: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        self.addCleanup(os.remove, path)
        return path

    def test_rejects_query_without_text(self) -> None:
        path = self._write("queries:\n  - query_id: q1\n    relevant: []\n")
        with self.assertRaises(ValueError):
            load_gold_set(path)

    def test_rejects_non_list_relevant(self) -> None:
        path = self._write("queries:\n  - query: hi\n    relevant: nope\n")
        with self.assertRaises(ValueError):
            load_gold_set(path)

    def test_missing_queries_key_defaults_to_empty(self) -> None:
        path = self._write("version: '1'\n")
        self.assertEqual(load_gold_set(path)["queries"], [])

    def test_real_gold_set_loads(self) -> None:
        repo_gold = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "examples",
            "eval",
            "gold_ga4gh.yaml",
        )
        data = load_gold_set(repo_gold)
        self.assertGreaterEqual(len(data["queries"]), 10)
        for q in data["queries"]:
            self.assertTrue(q.get("relevant"), f"{q.get('query_id')} has no anchors")


if __name__ == "__main__":
    unittest.main()
