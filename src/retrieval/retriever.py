"""
Retriever for querying relevant clauses from the vector store.

Connects to a persisted ChromaDB collection and performs similarity
search, returning results with source citations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import chromadb

from src.config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR, DEFAULT_TOP_K, EMBEDDING_MODEL
from src.ingestion.embedder import get_chroma_client, get_embedding_function


@dataclass
class RetrievalResult:
    """A single retrieval result with text and citation metadata."""

    text: str
    source: str
    distance: float
    metadata: dict

    def format_citation(self) -> str:
        """Format this result as a human-readable citation string."""
        display = self.metadata.get("display_name") or self.metadata.get("source", "Unknown")
        section = self.metadata.get("section")
        page = self.metadata.get("page")
        chunk = self.metadata.get("chunk_index", "?")

        citation = f"[{display}"
        if section:
            citation += f", {section}"
        elif page is not None:
            citation += f", Page {page}"
        citation += f", Chunk {chunk}]"
        return citation


class Retriever:
    """Queries the ChromaDB vector store for relevant policy clauses."""

    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        collection_name: str = CHROMA_COLLECTION_NAME,
        model_name: str = EMBEDDING_MODEL,
    ):
        self.client = get_chroma_client(persist_dir)
        self.embedding_fn = get_embedding_function(model_name)

        try:
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
            )
        except Exception:
            raise ValueError(
                f"Collection '{collection_name}' not found. "
                "Please ingest documents first using: python -m src.main ingest <file>"
            )

    def query(
        self,
        query_text: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[RetrievalResult]:
        """Search for document chunks most relevant to the query.

        Args:
            query_text: The user's question or consent form text.
            top_k: Number of results to return.

        Returns:
            List of RetrievalResult objects sorted by relevance.
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k,
        )

        retrieval_results: List[RetrievalResult] = []

        if results and results["documents"]:
            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)
            distances = results["distances"][0] if results["distances"] else [0.0] * len(documents)

            for doc_text, metadata, distance in zip(documents, metadatas, distances):
                retrieval_results.append(
                    RetrievalResult(
                        text=doc_text,
                        source=metadata.get("source", "Unknown"),
                        distance=distance,
                        metadata=metadata,
                    )
                )

        return retrieval_results

    def get_collection_count(self) -> int:
        """Return the number of documents in the collection."""
        return self.collection.count()

    def get_collection_stats(self) -> dict:
        """Return collection statistics including documents and categories.

        Returns:
            Dict with 'count', 'documents' (unique display names),
            and 'categories' (unique category values).
        """
        count = self.collection.count()
        if count == 0:
            return {"count": 0, "documents": [], "categories": []}

        # Fetch all metadata from the collection
        all_data = self.collection.get(include=["metadatas"])
        metadatas = all_data.get("metadatas", [])

        documents = sorted({
            m.get("display_name", m.get("source", "Unknown"))
            for m in metadatas if m
        })
        categories = sorted({
            m.get("category", "unknown")
            for m in metadatas if m
        })

        return {
            "count": count,
            "documents": documents,
            "categories": categories,
        }
