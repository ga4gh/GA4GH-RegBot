"""Tests for policy ingestion edge cases."""

import os
import tempfile
import unittest
from unittest.mock import patch


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


if __name__ == "__main__":
    unittest.main()


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
