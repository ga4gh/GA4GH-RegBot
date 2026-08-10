"""Tests for policy ingestion edge cases."""

import os
import tempfile
import unittest
from unittest.mock import patch


class TestPortableManifest(unittest.TestCase):
    def test_source_id_depends_on_content_not_absolute_path(self) -> None:
        from src.regbot.ingestion import _stable_source_id

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = os.path.join(first, "policy.txt")
            second_path = os.path.join(second, "policy.txt")
            for path in (first_path, second_path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("The same authoritative policy text.")
            self.assertEqual(_stable_source_id(first_path), _stable_source_id(second_path))

            with open(second_path, "w", encoding="utf-8") as f:
                f.write("A revised authoritative policy text.")
            self.assertNotEqual(_stable_source_id(first_path), _stable_source_id(second_path))

    def test_write_manifest_strips_legacy_source_path(self) -> None:
        from src.regbot.ingestion import read_manifest, write_manifest

        chunks = [
            {
                "id": "policy_c0",
                "text": "Policy text",
                "metadata": {"source": "policy.txt", "source_path": "/private/policy.txt"},
            }
        ]
        with tempfile.TemporaryDirectory() as store:
            write_manifest(store, chunks)
            metadata = read_manifest(store)[0]["metadata"]
        self.assertNotIn("source_path", metadata)


class TestIngestionPdf(unittest.TestCase):
    def test_empty_pdf_text_raises_clear_error(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            with tempfile.TemporaryDirectory() as store:
                with patch(
                    "src.regbot.ingestion.load_document_pages",
                    return_value=[("", 1)],
                ):
                    from src.regbot.ingestion import ingest_policy_file

                    with self.assertRaises(ValueError) as ctx:
                        ingest_policy_file(path, store)
                    msg = str(ctx.exception).lower()
                    self.assertIn("extractable text", msg)
                    self.assertIn("pdf", msg)
        finally:
            os.unlink(path)


class TestNothingIndexed(unittest.TestCase):
    """A document that indexes nothing must say so instead of returning 0 quietly."""

    def test_all_chunks_filtered_raises(self) -> None:
        from src.regbot.ingestion import ingest_policy_file

        with tempfile.TemporaryDirectory() as store:
            path = os.path.join(store, "toc.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Part I\n\nPart II\n\nPart III\n")
            with self.assertRaises(ValueError) as ctx:
                ingest_policy_file(path, store)
            msg = str(ctx.exception).lower()
            self.assertIn("nothing was indexed", msg)
            self.assertIn("toc.txt", msg)

    def test_empty_text_file_raises(self) -> None:
        from src.regbot.ingestion import ingest_policy_file

        with tempfile.TemporaryDirectory() as store:
            path = os.path.join(store, "blank.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("   \n\n")
            with self.assertRaises(ValueError) as ctx:
                ingest_policy_file(path, store)
            self.assertIn("no text", str(ctx.exception).lower())


class TestRunningHeaderRemoval(unittest.TestCase):
    """PDF page headers must not reach chunk text."""

    def test_repeated_short_line_is_stripped(self) -> None:
        from src.regbot.ingestion import _running_lines, _strip_running_lines

        pages = [f"CONSENT POLICY\nbody of page {i} with real content here." for i in range(6)]
        running = _running_lines(pages)
        self.assertIn("CONSENT POLICY", running)
        self.assertNotIn("CONSENT POLICY", _strip_running_lines(pages[0], running))
        self.assertIn("body of page 0", _strip_running_lines(pages[0], running))

    def test_long_repeated_line_is_kept(self) -> None:
        # Body text can legitimately repeat; only short lines are treated as furniture.
        from src.regbot.ingestion import _running_lines

        long_line = "This substantive sentence about data protection obligations repeats verbatim."
        self.assertNotIn(long_line, _running_lines([long_line] * 6))

    def test_short_documents_are_left_alone(self) -> None:
        from src.regbot.ingestion import _running_lines

        self.assertEqual(_running_lines(["Header\nbody"] * 2), set())

    def test_line_on_a_minority_of_pages_is_kept(self) -> None:
        from src.regbot.ingestion import _running_lines

        pages = ["Appendix\nbody"] + ["other body text here"] * 9
        self.assertNotIn("Appendix", _running_lines(pages))


class TestPdfTextCleanup(unittest.TestCase):
    def test_statutory_contents_pages_are_removed_before_operative_text(self) -> None:
        from src.regbot.ingestion import _strip_pdf_front_matter

        pages = [
            "Cover page",
            "ARRANGEMENT OF SECTIONS\n1. Short title\n2. Interpretation",
            "Part 2\n3. Consent\n4. Protection",
            "An Act to regulate health information.\nBe it enacted by Parliament",
            "1. This Act is the Health Information Act.",
        ]
        cleaned = _strip_pdf_front_matter(pages)
        self.assertEqual(cleaned[:3], ["", "", ""])
        self.assertIn("An Act to", cleaned[3])
        self.assertEqual(cleaned[4], pages[4])

    def test_non_statutory_document_is_unchanged(self) -> None:
        from src.regbot.ingestion import _strip_pdf_front_matter

        pages = ["Contents", "Policy recommendations", "Substantive guidance"]
        self.assertEqual(_strip_pdf_front_matter(pages), pages)

    def test_dotted_table_of_contents_is_removed_before_preamble(self) -> None:
        from src.regbot.ingestion import _strip_pdf_front_matter

        pages = [
            "Guidelines cover",
            "Table of Contents\nPreamble ........ 1\nChapter 1 ........ 3\nChapter 2 ........ 8",
            "More entries ........ 10\nConsent ........ 12\nReview ........ 14",
            "1 Preamble Through the development of medical science, these guidelines apply.",
        ]
        cleaned = _strip_pdf_front_matter(pages)
        self.assertEqual(cleaned[:3], ["", "", ""])
        self.assertTrue(cleaned[3].startswith("1 Preamble"))

    def test_audited_pypdf_word_splits_are_repaired(self) -> None:
        from src.regbot.ingestion import _repair_pdf_text

        text = "ST A TUTES: an of fence may be subject to re view by a Resear ch officer."
        repaired = _repair_pdf_text(text)
        self.assertIn("STATUTES", repaired)
        self.assertIn("offence", repaired)
        self.assertIn("review", repaired)
        self.assertIn("Research", repaired)


class TestCitableContent(unittest.TestCase):
    """Structural leftovers are not evidence; genuinely short provisions are."""

    def test_rejects_page_labels_and_provenance(self) -> None:
        from src.regbot.ingestion import has_citable_content

        for junk in (
            "9 Appendix 2",
            "Source: https://publications.europa.eu/resource/celex/32016R0679",
            "--- Retrieved: 2026-07-28",
        ):
            self.assertFalse(has_citable_content(junk), f"accepted junk: {junk!r}")

    def test_keeps_genuinely_short_provisions(self) -> None:
        from src.regbot.ingestion import has_citable_content

        # Taiwan PDPA Article 36 really is one sentence — dropping a rule is the worse error.
        self.assertTrue(
            has_citable_content(
                "Article 36 The statute of limitation for each data subject to exercise "
                "the right to claim damages shall be calculated separately."
            )
        )

    def test_url_does_not_count_towards_the_word_budget(self) -> None:
        from src.regbot.ingestion import has_citable_content

        self.assertFalse(
            has_citable_content("See https://example.org/a/very/long/path/with/many/segments")
        )

    def test_keeps_cjk_provision_without_whitespace(self) -> None:
        from src.regbot.ingestion import has_citable_content

        self.assertTrue(
            has_citable_content(
                "第三十七条网络数据处理者向境外提供重要数据的，应当通过数据出境安全评估。"
            )
        )
        self.assertFalse(has_citable_content("第三章重要数据安全"))


if __name__ == "__main__":
    unittest.main()
