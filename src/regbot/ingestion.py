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
from src.regbot.jurisdiction import normalize_jurisdiction
from src.regbot.text_utils import chunk_by_sections, detect_headings, sections_for_span


def _stable_source_id(path: str) -> str:
    base = os.path.basename(path)
    h = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:12]
    return f"{base}_{h}"


def _load_plaintext(path: str) -> List[Tuple[str, int]]:
    """Return list of (page_text, page_number); page_number 0 for plain files."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return [(f.read(), 0)]


def _running_lines(pages: List[str], *, min_pages: int = 3, ratio: float = 0.5) -> set:
    """
    Lines repeated on at least ``ratio`` of pages — running headers and footers.

    Every page of the GA4GH Consent Policy carries "CONSENT POLICY" as a header, which
    ``pypdf`` extracts as body text. Left in, it lands at the top of most chunks from that
    document: it pollutes the embedding, inflates BM25 on a meaningless term, and can be
    picked as a chunk's verbatim quote. One chunk consisted of nothing else.
    """
    if len(pages) < min_pages:
        return set()
    counts: Dict[str, int] = {}
    for page in pages:
        seen = set()
        for raw in page.split("\n"):
            line = " ".join(raw.split())
            # Long lines are body text even if a page repeats one; short ones are furniture.
            if not line or len(line) > 70 or line in seen:
                continue
            seen.add(line)
            counts[line] = counts.get(line, 0) + 1
    threshold = max(min_pages, int(len(pages) * ratio))
    return {line for line, n in counts.items() if n >= threshold}


def _strip_running_lines(page: str, running: set) -> str:
    if not running:
        return page
    kept = [raw for raw in page.split("\n") if " ".join(raw.split()) not in running]
    return "\n".join(kept)


def _load_pdf(path: str) -> List[Tuple[str, int]]:
    reader = PdfReader(path)
    raw_pages = [(page.extract_text() or "") for page in reader.pages]
    running = _running_lines(raw_pages)
    return [(_strip_running_lines(t, running), i + 1) for i, t in enumerate(raw_pages)]


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
    jurisdiction: Optional[str] = None,
    document_id: Optional[str] = None,
    framework: Optional[str] = None,
    content_type: Optional[str] = None,
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
    jurisdiction_tag = (
        normalize_jurisdiction(jurisdiction) if jurisdiction and str(jurisdiction).strip() else None
    )

    new_records: List[Dict[str, Any]] = []
    ext = os.path.splitext(file_path)[1].lower()
    pages = load_document_pages(file_path)
    chunk_idx = 0
    for page_text, page_num in pages:
        headings = detect_headings(page_text)
        for piece, offset in chunk_by_sections(page_text):
            cid = f"{source_tag}_p{page_num}_c{chunk_idx}"
            chunk_idx += 1
            meta: Dict[str, Any] = {
                "source": os.path.basename(file_path),
                "source_path": os.path.abspath(file_path),
                "page": int(page_num),
                "category": base_category,
            }
            # Absent when the source has no detectable heading structure (e.g. PDF text
            # extraction flattens layout). Omitted rather than guessed. A chunk that
            # straddles a boundary lists every section it touches, joined by "; ",
            # rather than claiming only the one it started in.
            spanned = sections_for_span(headings, offset, offset + len(piece))
            if spanned:
                meta["section"] = "; ".join(spanned)
            if jurisdiction_tag:
                meta["jurisdiction"] = jurisdiction_tag
            if document_id and str(document_id).strip():
                meta["document_id"] = str(document_id).strip()
            if framework and str(framework).strip():
                meta["framework"] = str(framework).strip()
            # Provenance: 'primary' = source regulatory text, 'summary' = contributor-written
            # paraphrase. Citations to a summary are not citations to the underlying clause,
            # so reviewers must be able to tell the two apart.
            if content_type and str(content_type).strip():
                meta["content_type"] = str(content_type).strip().lower()
            new_records.append(
                {
                    "id": cid,
                    "text": piece,
                    "metadata": meta,
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
