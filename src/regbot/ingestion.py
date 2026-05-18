from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

from src.regbot.config import (
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    MANIFEST_NAME,
    chromadb_settings,
)
from src.regbot.embeddings import load_sentence_transformer
from src.regbot.text_utils import chunk_text


def _stable_source_id(path: str) -> str:
    base = os.path.basename(path)
    h = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:12]
    return f"{base}_{h}"


def _load_plaintext(path: str) -> List[Tuple[str, int]]:
    """Return list of (page_text, page_number); page_number 0 for plain files."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return [(f.read(), 0)]


def _load_pdf(path: str) -> List[Tuple[str, int]]:
    reader = PdfReader(path)
    pages: List[Tuple[str, int]] = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        pages.append((t, i + 1))
    return pages


def load_document_pages(path: str) -> List[Tuple[str, int]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _load_pdf(path)
    return _load_plaintext(path)


def _manifest_path(store_dir: str) -> str:
    return os.path.join(store_dir, MANIFEST_NAME)


def _chroma_path(store_dir: str) -> str:
    return os.path.join(store_dir, CHROMA_SUBDIR)


def read_manifest(store_dir: str) -> List[Dict[str, Any]]:
    mp = _manifest_path(store_dir)
    if not os.path.isfile(mp):
        return []
    with open(mp, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("chunks", []))


def write_manifest(store_dir: str, chunks: List[Dict[str, Any]]) -> None:
    os.makedirs(store_dir, exist_ok=True)
    with open(_manifest_path(store_dir), "w", encoding="utf-8") as f:
        json.dump({"chunks": chunks}, f, ensure_ascii=False, indent=2)


def ingest_policy_file(
    file_path: str,
    store_dir: str,
    *,
    collection_name: str = DEFAULT_COLLECTION,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    category: Optional[str] = None,
    reset: bool = False,
) -> int:
    """
    Load a policy PDF or text file, chunk, embed, and persist to Chroma + manifest.
    Returns number of chunks written.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    import chromadb  # lazy import for environments with mixed pydantic stacks

    os.makedirs(store_dir, exist_ok=True)
    chroma_dir = _chroma_path(store_dir)

    client = chromadb.PersistentClient(path=chroma_dir, settings=chromadb_settings())
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        if os.path.isfile(_manifest_path(store_dir)):
            os.remove(_manifest_path(store_dir))

    existing = read_manifest(store_dir) if not reset else []
    source_tag = _stable_source_id(file_path)
    base_category = category or os.path.splitext(os.path.basename(file_path))[0]

    new_records: List[Dict[str, Any]] = []
    ext = os.path.splitext(file_path)[1].lower()
    pages = load_document_pages(file_path)
    chunk_idx = 0
    for page_text, page_num in pages:
        for piece in chunk_text(page_text):
            cid = f"{source_tag}_p{page_num}_c{chunk_idx}"
            chunk_idx += 1
            new_records.append(
                {
                    "id": cid,
                    "text": piece,
                    "metadata": {
                        "source": os.path.basename(file_path),
                        "source_path": os.path.abspath(file_path),
                        "page": int(page_num),
                        "category": base_category,
                    },
                }
            )

    if not new_records:
        if ext == ".pdf":
            total_chars = sum(len((t or "").strip()) for t, _ in pages)
            if total_chars == 0:
                raise ValueError(
                    "No extractable text from this PDF (0 characters after stripping). "
                    "The file may be scanned images only, encrypted, or corrupt; try OCR, "
                    "another PDF export, or a text-based source."
                )
        write_manifest(store_dir, existing)
        return 0

    model = load_sentence_transformer(embedding_model_name)
    texts = [r["text"] for r in new_records]
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[r["id"] for r in new_records],
        documents=texts,
        embeddings=embeddings,
        metadatas=[r["metadata"] for r in new_records],
    )

    merged = existing + new_records
    write_manifest(store_dir, merged)
    return len(new_records)
