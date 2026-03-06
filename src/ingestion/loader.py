"""
Document loader for GA4GH policy documents.

Supports loading PDF and plain-text files, returning structured documents
with source metadata for downstream chunking and embedding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Document:
    """A loaded document with its text content and source metadata."""

    text: str
    metadata: dict = field(default_factory=dict)


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

    return [
        Document(
            text=text,
            metadata={"source": path.name, "type": "text"},
        )
    ]


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
            documents.append(
                Document(
                    text=page_text,
                    metadata={
                        "source": path.name,
                        "type": "pdf",
                        "page": page_num,
                    },
                )
            )

    if not documents:
        raise ValueError(f"No readable text found in PDF: {path}")

    return documents


def load_document(file_path: str | Path) -> List[Document]:
    """Auto-detect file type and load accordingly.

    Args:
        file_path: Path to a .txt or .pdf file.

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
