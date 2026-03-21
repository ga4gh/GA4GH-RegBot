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

def detect_section(text: str) -> str:
    """
        Detect the nearest section heading in the first 300 characters of a chunk.

        Matches three heading formats:
        - Roman numeral or numeric sections: 'Section IV', 'Section 3.2'
        - Article headings: 'Article 5'
        - Numbered clauses with capitalised title: '3.1.2 Data Sharing'

        Returns the matched heading truncated to 100 characters, or 'N/A' if
        no heading is found. Used to populate chunk metadata for citation grounding.

        Args:
            text: Raw text content of a single document chunk.

        Returns:
            Detected section heading string, or 'N/A'.
        """
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
    """
    Load a single GA4GH policy PDF and split it into metadata-annotated chunks.

    Loads the PDF page by page via PyPDFLoader, then splits using
    RecursiveCharacterTextSplitter with CHUNK_SIZE and CHUNK_OVERLAP from config.
    Every chunk is annotated with five metadata fields driven by config.py mappings:
    filename, source (human-readable document name), category, subcategory
    (study-type scope e.g. 'pediatric'), and detected section heading.
    The page field is set by PyPDFLoader and preserved.

    Args:
        filepath: Absolute or relative path to the PDF file.

    Returns:
        List of LangChain Document objects with metadata attached.
    """
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
    """
    Load and chunk all PDFs in FRAMEWORKS_PATH.

    Iterates over every .pdf file in the configured frameworks directory in
    sorted order (consistent across runs) and calls load_and_chunk_pdf
    for each file. Skips non-PDF files including duo.csv.

    Returns:
        Combined list of all Document chunks across all ingested PDFs.

    Raises:
        FileNotFoundError: If no PDF files are found in FRAMEWORKS_PATH.
    """
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




