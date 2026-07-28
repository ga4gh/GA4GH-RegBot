import unittest

from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.study_type import detect_study_type
from src.regbot.text_utils import (
    chunk_spans,
    chunk_text,
    chunk_by_sections,
    detect_headings,
    is_hard_wrapped,
    section_for_offset,
    sections_for_span,
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


STATUTE_DOC = """Article 8

Conditions applicable to child's consent

1. Where point (a) of Article 6(1) applies, the processing shall be lawful.

Article 9

Processing of special categories of personal data

1. Processing of personal data revealing racial or ethnic origin shall be prohibited.
"""


class TestHeadingMerge(unittest.TestCase):
    def test_designation_and_title_are_joined(self) -> None:
        found = [h for _, h in detect_headings(STATUTE_DOC)]
        self.assertIn("Article 9 — Processing of special categories of personal data", found)
        self.assertNotIn("Article 9", found)

    def test_merge_stops_at_two_parts(self) -> None:
        # A third adjacent heading must not be swallowed into the label.
        doc = "Article 4\n\nDefinitions\n\nFor the purposes of this Regulation\n\nbody text here.\n"
        for _, h in detect_headings(doc):
            self.assertLessEqual(h.count(" — "), 1, f"over-merged: {h!r}")

    def test_headings_separated_by_body_are_not_merged(self) -> None:
        found = [h for _, h in detect_headings(STATUTE_DOC)]
        self.assertIn("Article 8 — Conditions applicable to child's consent", found)


class TestSectionsForSpan(unittest.TestCase):
    def test_reports_every_section_the_span_touches(self) -> None:
        headings = [(0, "Article 8"), (100, "Article 9"), (400, "Article 10")]
        self.assertEqual(sections_for_span(headings, 50, 200), ["Article 8", "Article 9"])

    def test_span_inside_one_section(self) -> None:
        headings = [(0, "Article 8"), (400, "Article 9")]
        self.assertEqual(sections_for_span(headings, 50, 200), ["Article 8"])

    def test_span_before_the_first_heading_reports_only_what_it_runs_into(self) -> None:
        headings = [(100, "Article 9")]
        self.assertEqual(sections_for_span(headings, 0, 200), ["Article 9"])

    def test_no_duplicates(self) -> None:
        headings = [(0, "Same"), (100, "Same")]
        self.assertEqual(sections_for_span(headings, 0, 200), ["Same"])

    def test_empty_when_no_headings(self) -> None:
        self.assertEqual(sections_for_span([], 0, 500), [])

    def test_straddling_chunk_does_not_claim_only_its_start(self) -> None:
        # Regression: a 900-char window opened in Article 8 and closed in Article 9 used to
        # be labelled "Article 8" alone — a wrong section on text that is Article 9.
        headings = detect_headings(STATUTE_DOC)
        body = STATUTE_DOC.strip()
        start = body.index("1. Where point")
        end = body.index("racial")
        self.assertEqual(len(sections_for_span(headings, start, end)), 2)


class TestChunkBySections(unittest.TestCase):
    def test_each_chunk_stays_inside_one_article(self) -> None:
        pieces = chunk_by_sections(STATUTE_DOC, chunk_size=900, overlap=150)
        headings = detect_headings(STATUTE_DOC)
        for text, off in pieces:
            spanned = sections_for_span(headings, off, off + len(text))
            self.assertLessEqual(len(spanned), 1, f"chunk straddles sections: {spanned}")

    def test_falls_back_to_sliding_window_without_headings(self) -> None:
        plain = "word " * 500
        self.assertEqual(
            [c for c, _ in chunk_by_sections(plain)],
            [c for c, _ in chunk_spans(plain)],
        )

    def test_long_section_is_split_but_stays_in_its_section(self) -> None:
        doc = "Article 1\n\nTitle here\n\n" + ("clause text. " * 400)
        pieces = chunk_by_sections(doc, chunk_size=300, overlap=50)
        self.assertGreater(len(pieces), 1)
        headings = detect_headings(doc)
        for text, off in pieces:
            self.assertLessEqual(len(sections_for_span(headings, off, off + len(text))), 1)

    def test_offsets_locate_the_chunk(self) -> None:
        body = STATUTE_DOC.strip()
        for text, off in chunk_by_sections(STATUTE_DOC):
            self.assertIn(text[:30], body[off : off + len(text) + 5])

    def test_empty_input(self) -> None:
        self.assertEqual(chunk_by_sections(""), [])


class TestStudyType(unittest.TestCase):
    def test_detect_genomic(self) -> None:
        self.assertEqual(
            detect_study_type("We will perform whole genome sequencing on participants."),
            "genomic_research",
        )


if __name__ == "__main__":
    unittest.main()
