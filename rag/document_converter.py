from langchain.schema import Document


def clauses_to_documents(clauses):

    documents = []
    
    for clause in clauses:

        metadata = {
            "document": clause.document_name,
            "section": clause.section_number,
            "section_title": clause.section_title,
        }

        # Only include subsection if it exists
        if clause.subsection is not None:
            metadata["subsection"] = clause.subsection
        if clause.section_number in ["Preamble", "VI"]:
            continue

        doc = Document(
            page_content=clause.clause_text,
            metadata=metadata
        )

        documents.append(doc)

    return documents