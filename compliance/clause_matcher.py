from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


def match_clauses(framework_docs, research_chunks, embedding_model):

    research_embeddings = embedding_model.embed_documents(research_chunks)

    results = []

    for doc in framework_docs:

        clause_embedding = embedding_model.embed_query(doc.page_content)

        similarities = cosine_similarity(
            [clause_embedding],
            research_embeddings
        )[0]

        best_score = max(similarities)

        results.append({
            "clause": doc,
            "score": best_score
        })

    return results