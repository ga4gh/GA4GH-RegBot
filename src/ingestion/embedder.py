"""
Embedding generator and ChromaDB storage.

Converts text chunks into vector embeddings using sentence-transformers
and stores them in a ChromaDB collection for later retrieval.
"""

from __future__ import annotations

from typing import List

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from src.config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR, EMBEDDING_MODEL
from src.ingestion.loader import Document


def get_chroma_client(persist_dir: str = CHROMA_PERSIST_DIR) -> chromadb.ClientAPI:
    """Create or connect to a persistent ChromaDB client.

    Args:
        persist_dir: Directory where ChromaDB stores its data.

    Returns:
        A ChromaDB PersistentClient instance.
    """
    return chromadb.PersistentClient(path=persist_dir)


def get_embedding_function(
    model_name: str = EMBEDDING_MODEL,
) -> SentenceTransformerEmbeddingFunction:
    """Create a sentence-transformer embedding function for ChromaDB.

    Args:
        model_name: Name of the sentence-transformers model.

    Returns:
        An embedding function compatible with ChromaDB.
    """
    return SentenceTransformerEmbeddingFunction(model_name=model_name)


def embed_and_store(
    documents: List[Document],
    persist_dir: str = CHROMA_PERSIST_DIR,
    collection_name: str = CHROMA_COLLECTION_NAME,
    model_name: str = EMBEDDING_MODEL,
) -> int:
    """Embed document chunks and store them in ChromaDB.

    Args:
        documents: List of chunked Documents to embed and store.
        persist_dir: ChromaDB persistence directory.
        collection_name: Name of the ChromaDB collection.
        model_name: Sentence-transformer model for embeddings.

    Returns:
        Number of documents stored.
    """
    client = get_chroma_client(persist_dir)
    embedding_fn = get_embedding_function(model_name)

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
    )

    # Prepare batch data for ChromaDB
    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[dict] = []

    for i, doc in enumerate(documents):
        # Create a unique ID from source + chunk index
        source = doc.metadata.get("source", "unknown")
        chunk_idx = doc.metadata.get("chunk_index", i)
        doc_id = f"{source}_chunk_{chunk_idx}"

        ids.append(doc_id)
        texts.append(doc.text)
        metadatas.append(doc.metadata)

    if texts:
        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )

    return len(texts)
