from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from src.embeddings.embedder import load_embedder
from src.ingestion.vector_store import load_vectorstore


def load_retriever(semantic_k: int = 6, bm25_k: int = 6) -> EnsembleRetriever:
    """
    Build and return the hybrid EnsembleRetriever combining semantic and BM25 search.

    Loads the ChromaDB vectorstore and builds two retrievers over the same chunks:
    a semantic retriever using cosine similarity, and a BM25 retriever built from
    the same chunks already in ChromaDB without reloading any PDFs. Results from
    both are merged using Reciprocal Rank Fusion with equal 50/50 weighting.

    This hybrid approach is necessary for legal compliance use cases where pure
    semantic search fails to match exact legal terms like 'withdrawal', 'opt-out',
    and 'de-identification'.

    Args:
        semantic_k: Number of candidates for the semantic retriever. Defaults to 6.
        bm25_k:     Number of candidates for the BM25 retriever. Defaults to 6.

    Returns:
        EnsembleRetriever instance ready for compliance checking.
    """

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
    """
    Run hybrid search for a single compliance check and return the top k chunks.

    Runs the EnsembleRetriever against the query, then filters results by
    category and subcategory if provided. Category scopes retrieval to a document
    group (e.g. 'foundational_principles'). Subcategory scopes to a study type context
    (e.g. 'pediatric', 'familial'). Filtering happens post-retrieval on the
    merged ranked results.

    Args:
        retriever:   EnsembleRetriever instance from load_retriever().
        query:       Pre-written CHECK_QUERY string from config.py.
        category:    Optional metadata filter for document category.
        subcategory: Optional metadata filter for study type subcategory.
        k:           Maximum number of chunks to return. Defaults to 4.

    Returns:
        List of up to k LangChain Document objects with metadata attached.
    """
    results = retriever.get_relevant_documents(query)

    if category:
        results = [doc for doc in results if doc.metadata.get("category") == category]

    if subcategory:
        results = [doc for doc in results if doc.metadata.get("subcategory") == subcategory]

    return results[:k]