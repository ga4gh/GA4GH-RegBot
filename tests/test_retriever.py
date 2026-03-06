"""Tests for the retrieval pipeline (end-to-end with ChromaDB)."""

import shutil
from pathlib import Path

import pytest

from src.ingestion.chunker import chunk_documents
from src.ingestion.embedder import embed_and_store
from src.ingestion.loader import Document
from src.retrieval.retriever import Retriever, RetrievalResult


@pytest.fixture
def temp_chroma_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for ChromaDB persistence."""
    chroma_dir = tmp_path / "test_chroma_db"
    chroma_dir.mkdir()
    return chroma_dir


@pytest.fixture
def populated_retriever(temp_chroma_dir: Path) -> Retriever:
    """Create a retriever with sample GA4GH policy text already ingested."""
    sample_docs = [
        Document(
            text=(
                "Section 2.1: Informed Consent Requirements. "
                "Consent should be obtained from data donors or their authorized "
                "representatives before genomic and health-related data is collected "
                "for research purposes. The consent process should be clear, "
                "understandable, and culturally appropriate."
            ),
            metadata={"source": "ga4gh_framework.txt", "chunk_index": 0},
        ),
        Document(
            text=(
                "Section 4.1: Technical Safeguards. "
                "Organizations holding genomic data must implement appropriate "
                "technical measures, including encryption of data at rest and in "
                "transit, access controls and authentication mechanisms, audit "
                "trails for data access and modifications."
            ),
            metadata={"source": "ga4gh_framework.txt", "chunk_index": 1},
        ),
        Document(
            text=(
                "Section 3.3: Data Use Agreements. "
                "All data users must sign a Data Use Agreement specifying "
                "permitted uses of the data, restrictions on re-identification "
                "of data donors, requirements for data security and storage."
            ),
            metadata={"source": "ga4gh_framework.txt", "chunk_index": 2},
        ),
    ]

    collection_name = "test_collection"

    embed_and_store(
        sample_docs,
        persist_dir=str(temp_chroma_dir),
        collection_name=collection_name,
    )

    return Retriever(
        persist_dir=str(temp_chroma_dir),
        collection_name=collection_name,
    )


class TestRetriever:
    """Tests for the retrieval module."""

    def test_query_returns_results(self, populated_retriever: Retriever):
        """Querying should return relevant results."""
        results = populated_retriever.query("What are the consent requirements?")

        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_query_relevance(self, populated_retriever: Retriever):
        """The most relevant result should contain consent-related text."""
        results = populated_retriever.query("informed consent for data collection")

        assert len(results) > 0
        # The top result should be about consent (Section 2.1)
        top_text = results[0].text.lower()
        assert "consent" in top_text

    def test_security_query_relevance(self, populated_retriever: Retriever):
        """Querying about security should return security-related chunks."""
        results = populated_retriever.query("data encryption and security measures")

        assert len(results) > 0
        top_text = results[0].text.lower()
        assert "encryption" in top_text or "security" in top_text or "safeguard" in top_text

    def test_results_contain_source_metadata(self, populated_retriever: Retriever):
        """Each result should contain source metadata for citations."""
        results = populated_retriever.query("data use agreement")

        assert len(results) > 0
        for result in results:
            assert result.source == "ga4gh_framework.txt"
            assert "source" in result.metadata
            assert "chunk_index" in result.metadata

    def test_top_k_limits_results(self, populated_retriever: Retriever):
        """The top_k parameter should limit the number of results."""
        results = populated_retriever.query("data", top_k=2)
        assert len(results) <= 2

    def test_collection_count(self, populated_retriever: Retriever):
        """The collection should report the correct number of documents."""
        assert populated_retriever.get_collection_count() == 3


class TestRetrievalResult:
    """Tests for the RetrievalResult dataclass."""

    def test_format_citation_with_page(self):
        """Citation should include page number when available."""
        result = RetrievalResult(
            text="Some clause text",
            source="framework.pdf",
            distance=0.5,
            metadata={"source": "framework.pdf", "page": 5, "chunk_index": 2},
        )

        citation = result.format_citation()
        assert "framework.pdf" in citation
        assert "Page 5" in citation
        assert "Chunk 2" in citation

    def test_format_citation_without_page(self):
        """Citation should work without page number."""
        result = RetrievalResult(
            text="Some text",
            source="policy.txt",
            distance=0.3,
            metadata={"source": "policy.txt", "chunk_index": 0},
        )

        citation = result.format_citation()
        assert "policy.txt" in citation
        assert "Page" not in citation
        assert "Chunk 0" in citation
