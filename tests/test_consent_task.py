import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "experiments"))

from agreement import cohen_kappa  # noqa: E402
from consent_eval import gold_for, score_document, score_gaps  # noqa: E402
from consent_pipeline import _interleave, prepare_text, segment  # noqa: E402
from units import coarse_documents, judgment_units  # noqa: E402


def chunk(cid, doc, section, jur="EU"):
    return {
        "id": cid,
        "text": "x",
        "metadata": {"document_id": doc, "section": section, "jurisdiction": jur},
    }


class SegmentationTests(unittest.TestCase):
    def test_segment_keeps_short_headed_clause_and_merges_bare_title(self):
        text = (
            "Consent form\n\n"
            "1. Withdrawal\nYou may withdraw at any time and we will stop collecting new data from you.\n"
            "We will not be able to retrieve data that have already been shared with others.\n\n"
            "2. Contact\nQuestions may be directed to the coordinator.\n"
        )
        segs = segment(text)
        self.assertEqual(len(segs), 2)
        self.assertTrue(segs[0].startswith("Consent form\n1. Withdrawal"))
        self.assertTrue(segs[1].startswith("2. Contact"))

    def test_segment_splits_blank_line_paragraphs_without_headings(self):
        para = (
            "We will store your samples securely in the biobank for future approved research. " * 2
        )
        self.assertEqual(len(segment(f"{para}\n\n{para}")), 2)

    def test_prepare_text_markers_furniture_and_page_breaks(self):
        text = (
            "CONTENTS\nGENOMIC SEQUENCING .... 13\nHIV TESTING .... 17\n"
            "Study Form Page 1 of 3\nGENOMIC SEQUENCING\nWe will read your DNA.\n"
            "\f\nStudy Form Page 2 of 3\nThis continues the same paragraph.\n"
            "Study Form Page 3 of 3\nHIV TESTING\nNot part of the section.\n"
        )
        out = prepare_text(
            text,
            start_marker="GENOMIC SEQUENCING",
            start_occurrence=2,
            end_marker="HIV TESTING",
        )
        self.assertTrue(out.startswith("GENOMIC SEQUENCING"))
        self.assertNotIn("Not part of the section", out)
        self.assertNotIn("Page", out)  # running header removed (repeats with different numbers)
        self.assertNotIn("\f", out)
        self.assertIn("We will read your DNA.\nThis continues", out)

    def test_prepare_text_line_paragraphs_and_split_before(self):
        text = (
            "Intro paragraph. Example 1: first sample clause text here. "
            "Example 2: second sample clause."
        )
        out = prepare_text(text, line_paragraphs=True, split_before=[r"Example \d+:"])
        self.assertEqual(out.count("\n\n"), 2)
        segs = segment(out, min_chars=10)
        self.assertEqual([s.split(":")[0] for s in segs[1:]], ["Example 1", "Example 2"])

    def test_segment_splits_long_blocks_at_sentence_boundaries(self):
        sentence = "We will store your samples securely for many years in the biobank. "
        block = sentence * 30  # ~2,000 characters, no headings, no blank lines
        segs = segment(block, max_chars=600)
        self.assertGreaterEqual(len(segs), 3)
        self.assertTrue(all(len(s) <= 700 for s in segs))
        self.assertTrue(all(s.rstrip().endswith(".") for s in segs))
        self.assertEqual(" ".join(segs).split(), block.split())

    def test_question_and_caps_headings_start_clauses(self):
        text = (
            "What is All of Us?\nAll of Us is a health research program. "
            "If you join, we will gather data about you.\n"
            "How long will it last?\nAt least ten years. "
            "You can withdraw at any time if you decide to join the program.\n"
            "WHAT ARE MY OPTIONS? Taking part is your choice. "
            "You can choose to take part or not take part at all.\n"
        )
        segs = segment(text, min_chars=40)
        self.assertEqual(len(segs), 3)
        self.assertTrue(segs[1].startswith("How long will it last?"))
        self.assertTrue(segs[2].startswith("WHAT ARE MY OPTIONS?"))


class AllocationTests(unittest.TestCase):
    def test_interleave_round_robins_and_caps_per_provision(self):
        a = [
            chunk("a1", "gdpr", "Art 7"),
            chunk("a2", "gdpr", "Art 7"),
            chunk("a3", "gdpr", "Art 7"),
        ]
        b = [chunk("b1", "pipl", "Art 15")]
        out = _interleave([a, b], budget=10, cap=2)
        self.assertEqual([c["id"] for c in out], ["a1", "b1", "a2"])

    def test_interleave_respects_budget_and_dedups(self):
        a = [chunk("x", "d", "s1"), chunk("y", "d", "s2")]
        out = _interleave([a, a], budget=1)
        self.assertEqual([c["id"] for c in out], ["x"])


class ScoringTests(unittest.TestCase):
    def test_gold_is_union_of_cells_over_aspects_and_scope(self):
        cells = {
            "A08|EU": {"gdpr § Art 7"},
            "A08|CN": {"pipl § Art 15"},
            "A04|EU": {"gdpr § Art 46"},
        }
        doc = {"aspects": ["A08"], "scope": ["EU", "SG"]}
        self.assertEqual(gold_for(doc, cells), {"A08|EU": {"gdpr § Art 7"}, "A08|SG": set()})

    def test_score_document_counts_recall_coverage_precision_and_templates(self):
        doc_gold = {"A08|EU": {"gdpr § Art 7"}, "A04|EU": {"gdpr § Art 46"}, "A08|SG": set()}
        ranked = [
            chunk("1", "gdpr", "Art 7"),
            chunk("2", "tmpl", "Withdrawal"),
            chunk("3", "gdpr", "Art 5"),
        ]
        roles = {"tmpl": "template", "gdpr": "law"}
        s = score_document(ranked, doc_gold, roles, budget=3)
        self.assertAlmostEqual(s["provision_recall@3"], 0.5)
        self.assertAlmostEqual(s["cell_coverage@3"], 0.5)  # the empty SG cell is not counted
        self.assertAlmostEqual(s["cell_coverage_norm@3"], 0.5)  # ceiling is 1 when budget >= cells
        self.assertAlmostEqual(s["precision@3"], 1 / 3)
        self.assertAlmostEqual(s["template_rate@3"], 1 / 3)

    def test_gap_scores_against_complement_of_addressed_aspects(self):
        s = score_gaps(
            reported=["A10", "A13"], addressed=["A01", "A08"], taxonomy=["A01", "A08", "A10", "A11"]
        )
        self.assertAlmostEqual(s["gap_precision"], 0.5)
        self.assertAlmostEqual(s["gap_recall"], 0.5)

    def test_unstructured_documents_are_judged_per_chunk(self):
        flat = [{"id": f"f{i}", "text": "x", "metadata": {"document_id": "flat"}} for i in range(6)]
        law = [chunk(f"l{i}", "law", f"Art {i}") for i in range(6)]
        coarse = coarse_documents(flat + law)
        self.assertEqual(coarse, {"flat"})
        self.assertNotEqual(judgment_units(flat[0], coarse), judgment_units(flat[1], coarse))
        self.assertEqual(judgment_units(law[0], coarse), {"law § Art 0"})

    def test_cohen_kappa_known_values(self):
        self.assertAlmostEqual(cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]), 1.0)
        self.assertAlmostEqual(cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]), -1.0)
        # 2x2 example: po = 0.7, marginals 50/50 on both sides -> pe = 0.5 -> kappa = 0.4
        a = [1] * 50 + [0] * 50
        b = [1] * 35 + [0] * 15 + [1] * 15 + [0] * 35
        self.assertAlmostEqual(cohen_kappa(a, b), 0.4)


if __name__ == "__main__":
    unittest.main()
