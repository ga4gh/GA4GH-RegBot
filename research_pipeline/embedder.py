def embed_chunks(chunks, embedding_model):

    embeddings = embedding_model.embed_documents(chunks)

    return embeddings