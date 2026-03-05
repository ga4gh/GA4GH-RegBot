from langchain_community.vectorstores import Chroma
from config import CHROMA_PATH


def build_vectorstore(chunks: list, embedder) -> Chroma:
    """Embed all chunks and store in ChromaDB. Returns the vectorstore."""
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
    """Load an existing ChromaDB from disk. Used by retriever.py."""
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embedder,
    )