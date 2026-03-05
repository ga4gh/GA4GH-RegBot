from langchain_community.embeddings import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL

# Load and return the embedding model used for both indexing and search.
def load_embedder() -> HuggingFaceEmbeddings:
    """Initialize and return the embedding model."""
    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    return HuggingFaceEmbeddings(
        model_name    = EMBEDDING_MODEL,
        model_kwargs  = {"device": "cpu"},
        encode_kwargs = {"normalize_embeddings": True},
    )