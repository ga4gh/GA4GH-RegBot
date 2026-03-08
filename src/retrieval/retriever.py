from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from src.embeddings.embedder import load_embedder
from src.ingestion.vector_store import load_vectorstore


def load_retriever(semantic_k: int = 6, bm25_k: int = 6) -> EnsembleRetriever:
    """Build and return hybrid EnsembleRetriever. Call once at startup."""
    embedder    = load_embedder()
    vectorstore = load_vectorstore(embedder)

    semantic_retriever = vectorstore.as_retriever(
        search_kwargs={"k": semantic_k}
    )

    # BM25 indexes the same chunks already in ChromaDB — no PDF reload needed
    all_docs         = vectorstore.similarity_search("", k=vectorstore._collection.count())
    bm25_retriever   = BM25Retriever.from_documents(all_docs)
    bm25_retriever.k = bm25_k

    ensemble = EnsembleRetriever(
        retrievers = [semantic_retriever, bm25_retriever],
        weights    = [0.5, 0.5],
    )

    print(f"Retriever loaded: semantic + BM25 over {len(all_docs)} chunks")
    return ensemble


def retrieve(
    retriever,
    query:       str,
    category:    str = None,
    subcategory: str = None,
    k:           int = 4,
) -> list:
    """Run hybrid search for one compliance check. Returns top k chunks."""
    results = retriever.get_relevant_documents(query)

    if category:
        results = [doc for doc in results if doc.metadata.get("category") == category]

    if subcategory:
        results = [doc for doc in results if doc.metadata.get("subcategory") == subcategory]

    return results[:k]