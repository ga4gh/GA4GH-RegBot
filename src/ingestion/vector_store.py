from langchain_community.vectorstores import Chroma
from config import CHROMA_PATH


def build_vectorstore(chunks: list, embedder) -> Chroma:
    """
    Embed all document chunks and persist them to a local ChromaDB instance.

    Takes the full list of chunks produced by ingest_all_pdfs, each carrying filename,
    source, category, subcategory, section, and page metadata, generates vectors
    using the provided embedder, and stores everything in ChromaDB at CHROMA_PATH.
    Run once after ingestion - not called during compliance checking.

    Args:
        chunks: List of LangChain Document objects with metadata attached.
        embedder: HuggingFaceEmbeddings instance from load_embedder().

    Returns:
        Persisted Chroma vectorstore instance.
    """
    print(f"Embedding {len(chunks)} chunks and storing in ChromaDB...")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embedder,
        persist_directory=CHROMA_PATH,
    )

    print(f"ChromaDB built at: {CHROMA_PATH}")
    print(f"Total vectors stored: {vectorstore._collection.count()}")
    return vectorstore

def load_vectorstore(embedder) -> Chroma:
    """
    Load an existing ChromaDB vectorstore from disk.

    Reads the persisted vectorstore at CHROMA_PATH without re-embedding.
    Called by retriever.py at query time to initialise the semantic search
    component of the EnsembleRetriever.

    Args:
        embedder: HuggingFaceEmbeddings instance from load_embedder().
                  Must match the model used when the vectorstore was built.

    Returns:
        Chroma vectorstore instance ready for similarity search.
    """
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embedder,
    )