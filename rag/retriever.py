def search_framework(vectorstore, query):

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 5}
)
    results = retriever.invoke(query)

    return results