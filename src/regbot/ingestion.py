from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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

# Malformed decorative image streams in some official PDFs do not affect extracted text;
# missing or unusable text is rejected by the citable-content checks below.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Minimum Latin-script words a chunk must carry to be worth citing. CJK text uses a
# character floor because whitespace is not a lexical delimiter in those languages.
MIN_CITABLE_WORDS = 10
MIN_CITABLE_CJK_CHARS = 20


def _stable_source_id(path: str) -> str:
    base = os.path.basename(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return f"{base}_{digest.hexdigest()[:12]}"


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


def _strip_pdf_front_matter(pages: List[str]) -> List[str]:
    """Remove recognized contents pages when a clear operative opening follows."""
    arrangement = next(
        (i for i, text in enumerate(pages[:12]) if "ARRANGEMENT OF SECTIONS" in text.upper()),
        None,
    )
    operative = None
    if arrangement is not None:
        operative = next(
            (
                i
                for i, text in enumerate(pages[arrangement + 1 : 20], start=arrangement + 1)
                if re.search(r"\bAn\s+Act\s+to\b", text, flags=re.IGNORECASE)
            ),
            None,
        )

    # Some official guidelines use conventional dotted-leader contents rather than the
    # statutory heading above. Only strip when a later page has an unmistakable Preamble
    # opening; a generic page titled "Contents" is not sufficient evidence by itself.
    if operative is None:
        contents = next(
            (
                i
                for i, text in enumerate(pages[:6])
                if "TABLE OF CONTENTS" in text.upper() and text.count("...") >= 3
            ),
            None,
        )
        if contents is not None:
            operative = next(
                (
                    i
                    for i, text in enumerate(pages[contents + 1 : 20], start=contents + 1)
                    if re.match(r"\s*\d*\s*Preamble\b", text, flags=re.IGNORECASE)
                ),
                None,
            )
    if operative is None:
        return pages
    return ["" if i < operative else text for i, text in enumerate(pages)]


def _repair_pdf_text(text: str) -> str:
    """Repair audited pypdf word splits without guessing arbitrary whitespace joins."""
    replacements = {
        r"\bST\s+A\s+TUTES\b": "STATUTES",
        r"\bof\s+fence\b": "offence",
        r"\bof\s+fences\b": "offences",
        r"\bof\s+ficer\b": "officer",
        r"\bof\s+ficers\b": "officers",
        r"\bof\s+fice\b": "office",
        r"\bre\s+view\b": "review",
        r"\brev\s+iew\b": "review",
        r"\br\s+eview\b": "review",
        r"\bResear\s+ch\b": "Research",
        r"\bresear\s+ch\b": "research",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def _load_pdf(path: str) -> List[Tuple[str, int]]:
    reader = PdfReader(path)
    raw_pages = [_repair_pdf_text(page.extract_text() or "") for page in reader.pages]
    raw_pages = _strip_pdf_front_matter(raw_pages)
    running = _running_lines(raw_pages)
    return [(_strip_running_lines(t, running), i + 1) for i, t in enumerate(raw_pages)]


def load_document_pages(path: str) -> List[Tuple[str, int]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _load_pdf(path)
    return _load_plaintext(path)


_URL_RE = re.compile(r"https?://\S+")


def has_citable_content(text: str, *, min_words: int = MIN_CITABLE_WORDS) -> bool:
    """
    False for chunks with too little prose to be worth citing.

    Catches the leftovers of document structure — a bare "9 Appendix 2" page label, or the
    provenance line a fetched file carries — which are indexable but useless as evidence:
    a reviewer offered one of them as the support for a recommendation learns nothing.

    Deliberately permissive. Several genuine provisions are very short (Taiwan PDPA
    Article 36 is a single sentence), and dropping a real rule is far worse than keeping a
    dull chunk, so only near-empty text is rejected.
    """
    stripped = _URL_RE.sub(" ", text)
    words = re.findall(r"[A-Za-z]{2,}", stripped)
    if len(words) >= min_words:
        return True
    # Han, Hiragana, Katakana and Hangul. A provision in these scripts may contain no
    # spaces at all; rejecting it for lacking English words discarded complete Chinese
    # regulations. Twenty characters still rejects bare labels such as “第三章”.
    cjk = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", stripped)
    return len(cjk) >= MIN_CITABLE_CJK_CHARS


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
    portable_chunks: List[Dict[str, Any]] = []
    for record in chunks:
        portable = dict(record)
        metadata = dict(record.get("metadata") or {})
        metadata.pop("source_path", None)
        portable["metadata"] = metadata
        portable_chunks.append(portable)
    os.makedirs(store_dir, exist_ok=True)
    with open(_manifest_path(store_dir), "w", encoding="utf-8") as f:
        json.dump({"chunks": portable_chunks}, f, ensure_ascii=False, indent=2)


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
            if not has_citable_content(piece):
                continue
            cid = f"{source_tag}_p{page_num}_c{chunk_idx}"
            chunk_idx += 1
            meta: Dict[str, Any] = {
                "source": os.path.basename(file_path),
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
        name = os.path.basename(file_path)
        total_chars = sum(len((t or "").strip()) for t, _ in pages)
        if total_chars == 0:
            if ext == ".pdf":
                raise ValueError(
                    "No extractable text from this PDF (0 characters after stripping). "
                    "The file may be scanned images only, encrypted, or corrupt; try OCR, "
                    "another PDF export, or a text-based source."
                )
            raise ValueError(f"{name} contains no text (0 characters after stripping).")
        # Text was extracted, but every chunk fell below the citable-content floor. Returning
        # 0 here left the caller with an unchanged store and no reason for it — the CLI even
        # exited 0. A document that indexes nothing is a failure, so it fails out loud.
        raise ValueError(
            f"{name}: extracted {total_chars} characters, but no chunk carries at least "
            f"{MIN_CITABLE_WORDS} citable words or equivalent CJK text, so nothing was "
            "indexed. This is usually a "
            "table of contents, a cover page, or a scan whose text needs OCR."
        )

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
