import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from parse.loader import load_framework_pdf
from parse.structural_chunking import parse_framework

from rag.document_converter import clauses_to_documents
from rag.embeddings import load_embedding_model
from rag.vector_store import create_vector_store

from research_pipeline.doc_loader import load_research_document
from research_pipeline.chunker import chunk_document

from compliance.clause_matcher import match_clauses
from compliance.gap_detector import detect_gaps
from compliance.report_generator import generate_report


def build_framework_index():

    print("\n--- Building Framework Knowledge Base ---\n")

    pages = load_framework_pdf("data/framework.pdf")

    full_text = ""
    for page in pages:
        full_text += page.page_content + "\n\n"

    clauses = parse_framework(full_text)

    print("Total Framework Clauses:", len(clauses))

    framework_docs = clauses_to_documents(clauses)

    embeddings = load_embedding_model()

    # optional vector DB
    create_vector_store(framework_docs, embeddings)

    print("\nFramework Knowledge Base Ready\n")

    return framework_docs, embeddings


def analyze_research_document(framework_docs, embeddings):

    print("\n--- Loading Research Document ---\n")

    research_text = load_research_document("data/research_doc.txt")

    research_chunks = chunk_document(research_text)

    print("Research Document Chunks:", len(research_chunks))

    match_results = match_clauses(framework_docs, research_chunks, embeddings)

    present, missing = detect_gaps(match_results)

    generate_report(present, missing, research_text)


def main():

    # Step 1: Build framework knowledge base
    framework_docs, embeddings = build_framework_index()

    # Step 2: Analyze researcher document
    analyze_research_document(framework_docs, embeddings)


if __name__ == "__main__":
    main()