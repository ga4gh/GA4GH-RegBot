from langchain_community.embeddings import HuggingFaceEmbeddings


def load_embedding_model():

    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5"
    )

    return embeddings