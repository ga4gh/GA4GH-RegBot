import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from parse.loader import load_framework_pdf
from parse.structural_chunking import parse_framework

from rag.document_converter import clauses_to_documents
from rag.embeddings import load_embedding_model

from research_pipeline.doc_loader import load_research_document
from research_pipeline.chunker import chunk_document

from compliance.clause_matcher import match_clauses
from compliance.gap_detector import detect_gaps


def build_kb():
    pages = load_framework_pdf("data/framework.pdf")

    text = "\n\n".join([p.page_content for p in pages])
    clauses = parse_framework(text)

    docs = clauses_to_documents(clauses)
    embeddings = load_embedding_model()

    return docs, embeddings


def evaluate(file_path, docs, embeddings):
    text = load_research_document(file_path)
    chunks = chunk_document(text)

    results = match_clauses(docs, chunks, embeddings)
    present, missing = detect_gaps(results)

    total = len(present) + len(missing)
    score = (len(present) / total) * 100 if total else 0

    return score, len(missing)


def run_tests():
    docs, embeddings = build_kb()

    folder = "tests/cases"

    print("\n=== Running RAG Tests ===\n")

    for file in os.listdir(folder):
        path = os.path.join(folder, file)

        score, missing = evaluate(path, docs, embeddings)

        print(f"{file} → Score: {score:.2f}% | Missing: {missing}")

        # basic assertions
        if "good" in file:
            assert score > 60

        if "bad" in file:
            assert score < 40


if __name__ == "__main__":
    run_tests()