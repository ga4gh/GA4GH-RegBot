import os
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config import (
    FRAMEWORKS_PATH,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    SOURCE_NAMES,
    CATEGORIES,
    SUBCATEGORIES,
)
# what abotu removing r"([A-Z][A-Z\s]{3,})\n" this match since it may not always represen a proper heading right
def detect_section(text: str) -> str:
    patterns = [
        r"(Section\s+[IVXLC\d]+[\.\d]*[^\n]*)",
        r"(Article\s+\d+[^\n]*)",
        r"(\d+\.\d+[\.\d]*\s+[A-Z][^\n]*)"
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:300])
        if match:
            return match.group(1).strip()[:100]
    return "N/A"

def load_and_chunk_pdf(filepath: str) -> list:
    """Load a single PDF, split into chunks, attach metadata. Returns list of Documents."""
    filename = os.path.basename(filepath)

    pages  = PyPDFLoader(filepath).load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    ).split_documents(pages)

    for chunk in chunks:
        chunk.metadata["filename"]    = filename
        chunk.metadata["source"]      = SOURCE_NAMES.get(filename, filename)
        chunk.metadata["category"]    = CATEGORIES.get(filename, "unknown")
        chunk.metadata["subcategory"] = SUBCATEGORIES.get(filename, "none")
        chunk.metadata["section"]     = detect_section(chunk.page_content)
        # chunk.metadata["page"] already set by PyPDFLoader

    print(f"{filename}: {len(pages)} pages :  {len(chunks)} chunks")
    return chunks

def ingest_all_pdfs() -> list:
    """Load and chunk all PDFs in FRAMEWORKS_PATH. Skips duo.csv. Returns all chunks."""
    pdf_files = [f for f in os.listdir(FRAMEWORKS_PATH) if f.endswith(".pdf")]

    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {FRAMEWORKS_PATH}.")

    print(f"Found {len(pdf_files)} PDF(s) in {FRAMEWORKS_PATH}\n")

    all_chunks = []
    # With sorted(), same order every run, predictable and debuggable
    for filename in sorted(pdf_files):
        all_chunks.extend(load_and_chunk_pdf(os.path.join(FRAMEWORKS_PATH, filename)))

    print(f"\nTotal chunks ready for embedding: {len(all_chunks)}")
    return all_chunks




