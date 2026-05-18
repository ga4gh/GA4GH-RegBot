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
