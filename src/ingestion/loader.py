"""
Document loader for GA4GH policy documents.

Supports loading PDF and plain-text files, returning structured documents
with enriched metadata (source, category, subcategory, section heading)
for downstream chunking, embedding, and citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.config import DOCUMENT_REGISTRY, FRAMEWORKS_DIR


@dataclass
class Document:
    """A loaded document with its text content and source metadata."""

    text: str
    metadata: dict = field(default_factory=dict)


def _lookup_registry(filename: str) -> dict:
    """Look up a filename in the document registry for category metadata.

    Matches on partial filename (the registry key just needs to appear
    somewhere in the filename).

    Returns:
        Dict with 'category', 'subcategory', 'display_name' if found,
        else empty dict.
    """
    for key, info in DOCUMENT_REGISTRY.items():
        if key.lower() in filename.lower():
            return dict(info)
    return {}


def _detect_section_heading(text: str) -> Optional[str]:
    """Detect the most prominent section heading in a text chunk.

    Looks for patterns like 'SECTION 1:', '1.1 Title', '## Heading', etc.

    Returns:
        The detected section heading string, or None.
    """
    # Pattern: 'SECTION N: TITLE' (our structured documents)
    match = re.search(r"SECTION\s+\d+:\s*(.+)", text)
    if match:
        return match.group(0).strip()

    # Pattern: 'N.N Title' (numbered subsections)
    match = re.search(r"^(\d+\.\d+)\s+(.+)", text, re.MULTILINE)
    if match:
        return f"{match.group(1)} {match.group(2).strip()}"

    # Pattern: '## Markdown heading'
    match = re.search(r"^#{1,3}\s+(.+)", text, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return None


def _enrich_metadata(metadata: dict) -> dict:
    """Enrich document metadata with registry info and section detection.

    Args:
        metadata: Base metadata dict with at least 'source' key.

    Returns:
        Enriched metadata dict.
    """
    source = metadata.get("source", "")
    registry_info = _lookup_registry(source)

    enriched = {**metadata}
    if registry_info:
        enriched["category"] = registry_info.get("category", "unknown")
        enriched["subcategory"] = registry_info.get("subcategory", "general")
        enriched["display_name"] = registry_info.get("display_name", source)
    else:
        enriched.setdefault("category", "unknown")
        enriched.setdefault("subcategory", "general")
        enriched.setdefault("display_name", source)

    return enriched


def load_text_file(file_path: str | Path) -> List[Document]:
    """Load a plain-text file and return it as a list of Documents.

    Each file is returned as a single Document. For multi-section files,
    use the chunker module to split into smaller pieces.

    Args:
        file_path: Path to the .txt file.

    Returns:
        List containing one Document with the full file text.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"File is empty: {path}")

    metadata = _enrich_metadata({"source": path.name, "type": "text"})

    return [Document(text=text, metadata=metadata)]


def load_pdf_file(file_path: str | Path) -> List[Document]:
    """Load a PDF file and return each page as a separate Document.

    Args:
        file_path: Path to the .pdf file.

    Returns:
        List of Documents, one per page, with page number metadata.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    from pypdf import PdfReader

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    reader = PdfReader(str(path))
    documents: List[Document] = []

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            metadata = _enrich_metadata({
                "source": path.name,
                "type": "pdf",
                "page": page_num,
            })
            documents.append(Document(text=page_text, metadata=metadata))

    if not documents:
        raise ValueError(f"No readable text found in PDF: {path}")

    return documents


def load_document(file_path: str | Path) -> List[Document]:
    """Auto-detect file type and load accordingly.

    Args:
        file_path: Path to a .txt, .md, or .pdf file.

    Returns:
        List of Documents from the file.

    Raises:
        ValueError: If the file extension is not supported.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return load_pdf_file(path)
    elif suffix in (".txt", ".md"):
        return load_text_file(path)
    else:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: .txt, .md, .pdf"
        )


def load_all_frameworks() -> List[Document]:
    """Load all documents from the data/frameworks/ directory.

    Returns:
        List of Documents from all supported files in frameworks/.
    """
    if not FRAMEWORKS_DIR.exists():
        raise FileNotFoundError(
            f"Frameworks directory not found: {FRAMEWORKS_DIR}"
        )

    all_docs: List[Document] = []
    supported = {".txt", ".md", ".pdf"}

    for file_path in sorted(FRAMEWORKS_DIR.iterdir()):
        if file_path.suffix.lower() in supported:
            try:
                docs = load_document(file_path)
                all_docs.extend(docs)
            except (ValueError, FileNotFoundError) as e:
                print(f"  Warning: Skipping {file_path.name}: {e}")

    return all_docs
