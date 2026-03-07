"""Tests for the document loader module."""

import tempfile
from pathlib import Path

import pytest

from src.ingestion.loader import Document, load_document, load_text_file


class TestLoadTextFile:
    """Tests for loading plain text files."""

    def test_load_text_file_returns_document(self, tmp_path: Path):
        """Loading a text file should return a Document with correct content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Section 1: Data Sharing\nThis is test content.")

        docs = load_text_file(test_file)

        assert len(docs) == 1
        assert "Data Sharing" in docs[0].text
        assert docs[0].metadata["source"] == "test.txt"
        assert docs[0].metadata["type"] == "text"

    def test_load_text_file_not_found(self):
        """Loading a nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_text_file("/nonexistent/file.txt")

    def test_load_text_file_empty(self, tmp_path: Path):
        """Loading an empty file should raise ValueError."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            load_text_file(test_file)


class TestLoadDocument:
    """Tests for the auto-detect load_document function."""

    def test_load_text_by_extension(self, tmp_path: Path):
        """The .txt extension should route to the text loader."""
        test_file = tmp_path / "policy.txt"
        test_file.write_text("GA4GH consent requirements.")

        docs = load_document(test_file)

        assert len(docs) == 1
        assert "consent" in docs[0].text.lower()

    def test_load_md_by_extension(self, tmp_path: Path):
        """The .md extension should also be supported."""
        test_file = tmp_path / "notes.md"
        test_file.write_text("# Framework Notes\nSome markdown content.")

        docs = load_document(test_file)
        assert len(docs) == 1

    def test_unsupported_extension(self, tmp_path: Path):
        """An unsupported extension should raise ValueError."""
        test_file = tmp_path / "data.csv"
        test_file.write_text("col1,col2")

        with pytest.raises(ValueError, match="Unsupported"):
            load_document(test_file)


class TestDocumentDataclass:
    """Tests for the Document dataclass."""

    def test_default_metadata(self):
        """Document should have empty dict as default metadata."""
        doc = Document(text="test")
        assert doc.metadata == {}

    def test_metadata_isolation(self):
        """Each Document should have its own metadata dict."""
        doc1 = Document(text="a")
        doc2 = Document(text="b")
        doc1.metadata["key"] = "value"
        assert "key" not in doc2.metadata
