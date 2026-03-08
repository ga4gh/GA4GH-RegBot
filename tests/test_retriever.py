import pytest
from src.retrieval.retriever import load_retriever, retrieve
from config import CHECK_QUERIES


@pytest.fixture(scope="module")
def retriever():
    return load_retriever()


def test_retriever_loads(retriever):
    assert retriever is not None


def test_retrieve_returns_results(retriever):
    results = retrieve(retriever, CHECK_QUERIES["withdrawal_rights"])
    assert len(results) > 0


def test_chunks_have_metadata(retriever):
    results = retrieve(retriever, CHECK_QUERIES["withdrawal_rights"])
    for doc in results:
        assert "source" in doc.metadata
        assert "category" in doc.metadata
        assert "subcategory" in doc.metadata
        assert "section" in doc.metadata


def test_k_respected(retriever):
    results = retrieve(retriever, CHECK_QUERIES["data_sharing_purpose"], k=2)
    assert len(results) <= 2


def test_category_filter(retriever):
    results = retrieve(retriever, CHECK_QUERIES["withdrawal_rights"], category="consent_requirements")
    for doc in results:
        assert doc.metadata.get("category") == "consent_requirements"


def test_subcategory_filter(retriever):
    results = retrieve(retriever, CHECK_QUERIES["minor_assent_process"], subcategory="pediatric")
    for doc in results:
        assert doc.metadata.get("subcategory") == "pediatric"


def test_bm25_catches_legal_terms(retriever):
    results = retrieve(retriever, "opt-out withdrawal consent")
    text = " ".join([doc.page_content.lower() for doc in results])
    assert any(term in text for term in ["withdraw", "opt-out", "opt out"])