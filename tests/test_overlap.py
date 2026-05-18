import unittest

from src.regbot.grounding import (
    filter_recommendations_by_token_overlap,
    max_token_recall_against_chunks,
)


class TestTokenOverlap(unittest.TestCase):
    def test_recall_high_when_text_matches_chunk(self) -> None:
        rec = "data sharing and participant consent withdrawal"
        chunk = "Participant consent and responsible data sharing practices."
        score = max_token_recall_against_chunks(rec, [chunk])
        self.assertGreater(score, 0.2)

    def test_recall_low_when_unrelated(self) -> None:
        rec = "qqqzzzaaabbb unrelated phrase xyzzy"
        chunk = "genomic data security measures for cloud storage participants"
        score = max_token_recall_against_chunks(rec, [chunk])
        self.assertLess(score, 0.05)

    def test_filter_drops_low_overlap(self) -> None:
        chunks = [
            {"id": "c1", "text": "International transfers require safeguards and transparency."},
        ]
        recs = [
            {
                "text": "completely unrelated vocabulary zyxwvut",
                "evidence_chunk_ids": ["c1"],
            }
        ]
        kept, meta = filter_recommendations_by_token_overlap(
            recs,
            chunks,
            min_overlap=0.15,
        )
        self.assertEqual(len(kept), 0)
        self.assertTrue(meta["dropped_all"])

    def test_filter_keeps_aligned_text(self) -> None:
        chunks = [
            {
                "id": "c1",
                "text": "International transfers require safeguards and transparency for participants.",
            },
        ]
        recs = [
            {
                "text": (
                    "Clarify international transfers and safeguards for participants "
                    "when data leaves the jurisdiction."
                ),
                "evidence_chunk_ids": ["c1"],
            }
        ]
        kept, meta = filter_recommendations_by_token_overlap(
            recs,
            chunks,
            min_overlap=0.06,
        )
        self.assertEqual(len(kept), 1)
        self.assertIn("token_overlap_score", kept[0])
        self.assertFalse(meta["dropped_all"])


if __name__ == "__main__":
    unittest.main()
