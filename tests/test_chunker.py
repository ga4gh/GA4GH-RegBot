"""Tests for the text chunking module."""

from pathlib import Path

from src.ingestion.chunker import chunk_documents
from src.ingestion.loader import Document


class TestChunkDocuments:
    """Tests for splitting documents into chunks."""

    def test_single_short_document_no_split(self):
        """A document shorter than chunk_size should remain as one chunk."""
        docs = [Document(text="Short text.", metadata={"source": "test.txt"})]

        chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=50)

        assert len(chunks) == 1
        assert chunks[0].text == "Short text."
        assert chunks[0].metadata["source"] == "test.txt"
        assert chunks[0].metadata["chunk_index"] == 0

    def test_long_document_is_split(self):
        """A long document should be split into multiple chunks."""
        long_text = "This is a sentence about data sharing. " * 50  # ~2000 chars
        docs = [Document(text=long_text, metadata={"source": "policy.txt"})]

        chunks = chunk_documents(docs, chunk_size=200, chunk_overlap=20)

        assert len(chunks) > 1
        # All chunks should have the source metadata
        for chunk in chunks:
            assert chunk.metadata["source"] == "policy.txt"
            assert "chunk_index" in chunk.metadata

    def test_metadata_preserved_through_chunking(self):
        """Original metadata should be carried through to all chunks."""
        docs = [
            Document(
                text="Word " * 200,
                metadata={"source": "framework.pdf", "page": 3, "type": "pdf"},
            )
        ]

        chunks = chunk_documents(docs, chunk_size=100, chunk_overlap=10)

        for chunk in chunks:
            assert chunk.metadata["source"] == "framework.pdf"
            assert chunk.metadata["page"] == 3
            assert chunk.metadata["type"] == "pdf"

    def test_chunk_indices_are_sequential(self):
        """Chunk indices should be sequential starting from 0."""
        docs = [Document(text="Word " * 200, metadata={"source": "test.txt"})]

        chunks = chunk_documents(docs, chunk_size=100, chunk_overlap=10)

        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_multiple_documents_chunked_independently(self):
        """Each document should have its own chunk_index sequence."""
        docs = [
            Document(text="First doc. " * 50, metadata={"source": "a.txt"}),
            Document(text="Second doc. " * 50, metadata={"source": "b.txt"}),
        ]

        chunks = chunk_documents(docs, chunk_size=200, chunk_overlap=20)

        # Both source files should be represented
        sources = {c.metadata["source"] for c in chunks}
        assert sources == {"a.txt", "b.txt"}

        # Each document's chunks should start from index 0
        for source in sources:
            source_chunks = [c for c in chunks if c.metadata["source"] == source]
            indices = [c.metadata["chunk_index"] for c in source_chunks]
            assert indices[0] == 0

    def test_empty_documents_list(self):
        """Chunking an empty list should return an empty list."""
        chunks = chunk_documents([])
        assert chunks == []
