from src.ingestion.pdf_loader   import ingest_all_pdfs
from src.embeddings.embedder    import load_embedder
from src.ingestion.vector_store import build_vectorstore

if __name__ == "__main__":
    chunks = ingest_all_pdfs()
    embedder = load_embedder()
    vectorstore = build_vectorstore(chunks, embedder)