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

        # use top-k average instead of max
        top_scores = sorted(similarities, reverse=True)[:3]
        best_score = np.mean(top_scores)

        results.append({
            "clause": doc,
            "score": best_score
        })

    return results