"""
Text chunker for splitting documents into smaller, overlapping pieces.

Uses LangChain's RecursiveCharacterTextSplitter to create chunks that
preserve semantic boundaries (paragraphs → sentences → words).
"""

from __future__ import annotations

from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import CHUNK_OVERLAP, CHUNK_SIZE
from src.ingestion.loader import Document


def chunk_documents(
    documents: List[Document],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Document]:
    """Split documents into smaller chunks with overlap.

    Each chunk inherits the metadata from its parent document, with an
    added ``chunk_index`` field for traceability.

    Args:
        documents: List of Documents to split.
        chunk_size: Maximum number of characters per chunk.
        chunk_overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of chunked Documents with preserved + extended metadata.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunked_docs: List[Document] = []

    for doc in documents:
        text_chunks = splitter.split_text(doc.text)

        for idx, chunk_text in enumerate(text_chunks):
            chunk_metadata = {**doc.metadata, "chunk_index": idx}
            chunked_docs.append(Document(text=chunk_text, metadata=chunk_metadata))

    return chunked_docs
