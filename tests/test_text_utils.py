import unittest

from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.study_type import detect_study_type
from src.regbot.text_utils import chunk_text, tokenize


class TestTextUtils(unittest.TestCase):
    def test_tokenize_basic(self) -> None:
        self.assertEqual(tokenize("Data Sharing (v2)"), ["data", "sharing", "v2"])

    def test_chunk_text_overlap(self) -> None:
        text = "a" * 100
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        self.assertGreaterEqual(len(chunks), 2)

    def test_rrf_orders_by_fusion(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], top_n=4)
        self.assertIn("b", fused[:2])


class TestStudyType(unittest.TestCase):
    def test_detect_genomic(self) -> None:
        self.assertEqual(
            detect_study_type("We will perform whole genome sequencing on participants."),
            "genomic_research",
        )


if __name__ == "__main__":
    unittest.main()
