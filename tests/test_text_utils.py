import unittest

from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.study_type import detect_study_type
from src.regbot.text_utils import (
    chunk_spans,
    chunk_text,
    detect_headings,
    is_hard_wrapped,
    section_for_offset,
    tokenize,
)

# Paragraph-structured source, as in the .txt corpus.
PARAGRAPH_DOC = """GA4GH GDPR Brief — Data Protection Impact Assessment
Source: https://example.org/brief
Tier: P1 | Jurisdiction: EU | Framework: GDPR

DISCLAIMER: Excerpted for RegBot corpus ingest. Not legal advice.

Article 35 of the GDPR requires data controllers to perform an assessment before processing likely to result in a high risk to rights and freedoms.

Applicability to genomic research

Large-scale genomic health research involving personal data will typically require a DPIA under the criteria set out by the supervisory authorities.

Timing and structure

DPIAs should be started early and updated continually as the processing evolves over the lifetime of the programme.
"""

# Hard-wrapped layout, as produced by pypdf: one line per visual line, breaking mid-clause.
WRAPPED_DOC = """Framework for Responsible Sharing of Genomic and Health-Related Data

the autonomous decision-making of data subjects while promoting the common good of

international data sharing, allowing everyone to share in the benefits of scientific

representative) who has had enough time, materials, and support to make an informed

progress and its applications as is their right and to partake in deliberation on how

these contributions can be respected across jurisdictions and research programmes

decision about whether to contribute data to a research programme or biobank network
"""


class TestTextUtils(unittest.TestCase):
    def test_tokenize_basic(self) -> None:
        self.assertEqual(tokenize("Data Sharing (v2)"), ["data", "sharing", "v2"])

    def test_chunk_text_overlap(self) -> None:
        text = "a" * 100
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        self.assertGreaterEqual(len(chunks), 2)

    def test_chunk_spans_offsets_locate_the_chunk(self) -> None:
        text = "abcdefghij" * 10
        for chunk, offset in chunk_spans(text, chunk_size=30, overlap=10):
            self.assertEqual(text[offset : offset + len(chunk)], chunk)

    def test_chunk_text_matches_chunk_spans(self) -> None:
        text = "word " * 400
        self.assertEqual(chunk_text(text, 100, 20), [c for c, _ in chunk_spans(text, 100, 20)])

    def test_rrf_orders_by_fusion(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], top_n=4)
        self.assertIn("b", fused[:2])


class TestHeadingDetection(unittest.TestCase):
    def test_finds_real_headings(self) -> None:
        found = [h for _, h in detect_headings(PARAGRAPH_DOC)]
        self.assertIn("Applicability to genomic research", found)
        self.assertIn("Timing and structure", found)

    def test_ignores_front_matter_key_value_lines(self) -> None:
        found = [h for _, h in detect_headings(PARAGRAPH_DOC)]
        for noise in ("Source: https://example.org/brief", "DISCLAIMER"):
            self.assertFalse(any(noise in h for h in found), f"{noise!r} treated as heading")
        self.assertFalse(any("|" in h for h in found))

    def test_hard_wrapped_text_yields_no_headings(self) -> None:
        # A wrong section label is worse than none: wrapped prose must produce nothing.
        self.assertTrue(is_hard_wrapped(WRAPPED_DOC.split("\n")))
        self.assertEqual(detect_headings(WRAPPED_DOC), [])

    def test_paragraph_text_is_not_flagged_as_wrapped(self) -> None:
        self.assertFalse(is_hard_wrapped(PARAGRAPH_DOC.split("\n")))

    def test_rejects_sentence_fragments_and_prose(self) -> None:
        for bad in (
            "the autonomous decision-making of data subjects while promoting",  # lowercase start
            "Consent is required. The controller must document it",  # two sentences
            "Representative) who has had enough time",  # unbalanced paren
            "Data may be shared with the",  # trailing continuation word
            "- Bullet item about consent",  # list marker
        ):
            doc = f"Intro paragraph here.\n\n{bad}\n\nMore body text follows here.\n"
            self.assertNotIn(bad, [h for _, h in detect_headings(doc)], f"accepted: {bad!r}")

    def test_empty_text_is_safe(self) -> None:
        self.assertEqual(detect_headings(""), [])
        self.assertEqual(detect_headings("   \n\n  "), [])


class TestSectionForOffset(unittest.TestCase):
    def test_returns_nearest_preceding_heading(self) -> None:
        headings = [(10, "First"), (100, "Second"), (200, "Third")]
        self.assertEqual(section_for_offset(headings, 150), "Second")
        self.assertEqual(section_for_offset(headings, 100), "Second")
        self.assertEqual(section_for_offset(headings, 500), "Third")

    def test_none_before_the_first_heading(self) -> None:
        self.assertIsNone(section_for_offset([(10, "First")], 5))

    def test_none_when_no_headings(self) -> None:
        self.assertIsNone(section_for_offset([], 42))

    def test_chunks_map_to_their_section(self) -> None:
        headings = detect_headings(PARAGRAPH_DOC)
        sections = {
            section_for_offset(headings, off)
            for _, off in chunk_spans(PARAGRAPH_DOC.strip(), chunk_size=120, overlap=20)
        }
        self.assertIn("Applicability to genomic research", sections)


class TestStudyType(unittest.TestCase):
    def test_detect_genomic(self) -> None:
        self.assertEqual(
            detect_study_type("We will perform whole genome sequencing on participants."),
            "genomic_research",
        )


if __name__ == "__main__":
    unittest.main()
