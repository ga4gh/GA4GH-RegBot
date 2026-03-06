"""
GA4GH RegBot — CLI Entry Point.

Usage:
    python -m src.main ingest <file_path>   Ingest a policy document into the vector store
    python -m src.main query "<question>"    Query the vector store for relevant clauses
    python -m src.main status               Show collection statistics
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.ingestion.loader import load_document, load_all_frameworks
from src.ingestion.chunker import chunk_documents
from src.ingestion.embedder import embed_and_store
from src.retrieval.retriever import Retriever


def cmd_ingest(file_path: str) -> None:
    """Ingest a document into the vector store."""
    path = Path(file_path)
    print(f"\n[*] Loading document: {path.name}")

    # Step 1: Load
    documents = load_document(file_path)
    print(f"   Loaded {len(documents)} document section(s)")

    # Step 2: Chunk
    chunks = chunk_documents(documents)
    print(f"   Split into {len(chunks)} chunks")

    # Step 3: Embed & Store
    print("   Generating embeddings and storing in ChromaDB...")
    count = embed_and_store(chunks)
    print(f"\n[OK] Successfully ingested {count} chunks from '{path.name}'")


def cmd_ingest_all() -> None:
    """Ingest all documents from the data/frameworks/ directory."""
    print("\n[*] Loading all GA4GH framework documents...")

    # Step 1: Load all
    documents = load_all_frameworks()
    if not documents:
        print("[!] No documents found in data/frameworks/. Run scripts/download_documents.py first.")
        return
    print(f"   Loaded {len(documents)} document section(s)")

    # Show per-source summary
    sources = {}
    for doc in documents:
        name = doc.metadata.get("display_name", doc.metadata.get("source", "?"))
        sources[name] = sources.get(name, 0) + 1
    print(f"\n   Documents found ({len(sources)}):")
    for name, count in sources.items():
        print(f"     - {name} ({count} section(s))")

    # Step 2: Chunk
    chunks = chunk_documents(documents)
    print(f"\n   Split into {len(chunks)} total chunks")

    # Step 3: Embed & Store
    print("   Generating embeddings and storing in ChromaDB...")
    stored = embed_and_store(chunks)
    print(f"\n[OK] Successfully ingested {stored} chunks from {len(sources)} documents")



def cmd_query(query_text: str, top_k: int = 5) -> None:
    """Query the vector store for relevant clauses."""
    print(f"\n[?] Searching for: \"{query_text}\"\n")

    retriever = Retriever()
    results = retriever.query(query_text, top_k=top_k)

    if not results:
        print("No results found. Have you ingested documents first?")
        print("  Run: python -m src.main ingest data/ga4gh_framework_excerpt.txt")
        return

    print(f"Found {len(results)} relevant clause(s):\n")
    print("=" * 70)

    for i, result in enumerate(results, 1):
        citation = result.format_citation()
        print(f"\n--- Result {i} {citation} ---")
        print(f"Distance: {result.distance:.4f}")
        print(f"\n{result.text}")
        print()

    print("=" * 70)


def cmd_status() -> None:
    """Show the current state of the vector store."""
    try:
        retriever = Retriever()
        count = retriever.get_collection_count()
        print("\n[i] Collection status:")
        print(f"   Documents stored: {count}")
        print(f"   Collection is ready for queries.")
    except ValueError as e:
        print(f"\n[!] {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="regbot",
        description="GA4GH RegBot — Compliance Assistant for Genomic Data Sharing",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a policy document")
    ingest_parser.add_argument("file", help="Path to the document (.txt, .md, or .pdf)")

    # query command
    query_parser = subparsers.add_parser("query", help="Query for relevant clauses")
    query_parser.add_argument("question", help="Your question or consent form text")
    query_parser.add_argument(
        "-k", "--top-k", type=int, default=5, help="Number of results (default: 5)"
    )

    # ingest-all command
    subparsers.add_parser(
        "ingest-all",
        help="Ingest all documents from data/frameworks/",
    )

    # status command
    subparsers.add_parser("status", help="Show vector store status")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args.file)
    elif args.command == "ingest-all":
        cmd_ingest_all()
    elif args.command == "query":
        cmd_query(args.question, top_k=args.top_k)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
