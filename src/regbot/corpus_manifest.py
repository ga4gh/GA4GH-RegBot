from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.regbot.config import DEFAULT_COLLECTION
from src.regbot.ingestion import ingest_policy_file
from src.regbot.jurisdiction import normalize_jurisdiction

_TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2}

_CORPUS_MANIFEST_HEADER = """\
# RegBot regulatory corpus inventory (GSoC 2026 Phase 1)
#
# Lists documents approved for ingest. Do not commit PDFs under data/corpus/;
# record URLs, licenses, and local paths used during ingest.
# See docs/DESIGN.md §3.1 and §5.1.
#
# Batch ingest:
#   python -m src.main ingest-manifest --manifest docs/corpus_manifest.yaml
#
# jurisdiction codes: SG, CN, TW, KR, JP, HK, EU, GA4GH, INTL
"""


def primary_jurisdiction(codes: Optional[List[str]]) -> Optional[str]:
    """Pick one chunk tag from a document-level jurisdiction list."""
    if not codes:
        return None
    normalized = [normalize_jurisdiction(str(c)) for c in codes if str(c).strip()]
    if not normalized:
        return None
    for code in normalized:
        if code != "INTL":
            return code
    return normalized[0]


def load_corpus_manifest(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Corpus manifest must be a mapping: {path}")
    docs = data.get("documents")
    if docs is None:
        data["documents"] = []
    elif not isinstance(docs, list):
        raise ValueError(f"'documents' must be a list in {path}")
    return data


def save_corpus_manifest(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    body = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(_CORPUS_MANIFEST_HEADER)
        f.write("\n")
        f.write(body)


def resolve_ingest_path(raw_path: str, *, manifest_path: str) -> str:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return str(path)
    manifest_dir = Path(manifest_path).resolve().parent
    repo_root = manifest_dir.parent
    candidates = [
        manifest_dir / path,
        repo_root / path,
        Path.cwd() / path,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return str((repo_root / path).resolve())


def _tier_sort_key(doc: Dict[str, Any]) -> Tuple[int, str]:
    tier = str(doc.get("tier") or "P9").upper()
    return (_TIER_ORDER.get(tier, 9), str(doc.get("document_id") or ""))


def ingest_from_corpus_manifest(
    manifest_path: str,
    store_dir: str,
    *,
    collection_name: str = DEFAULT_COLLECTION,
    embedding_model_name: Optional[str] = None,
    reset: bool = False,
    skip_ingested: bool = True,
    tier: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Ingest documents listed in corpus_manifest.yaml (P0 → P1 → P2 order).
    Updates ingested_at in the manifest when ingest succeeds (unless dry_run).
    """
    data = load_corpus_manifest(manifest_path)
    documents: List[Dict[str, Any]] = list(data.get("documents") or [])
    tier_filter = tier.upper() if tier else None

    selected: List[Dict[str, Any]] = []
    for doc in documents:
        if tier_filter and str(doc.get("tier") or "").upper() != tier_filter:
            continue
        if skip_ingested and doc.get("ingested_at"):
            continue
        ingest_path = doc.get("ingest_path")
        if not ingest_path or not str(ingest_path).strip():
            continue
        selected.append(doc)
    selected.sort(key=_tier_sort_key)

    results: List[Dict[str, Any]] = []
    first = True
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for doc in selected:
        doc_id = str(doc.get("document_id") or "")
        raw_path = str(doc.get("ingest_path"))
        resolved = resolve_ingest_path(raw_path, manifest_path=manifest_path)
        jurisdiction = primary_jurisdiction(doc.get("jurisdiction"))
        category = doc_id or None
        framework = doc.get("framework")
        if isinstance(framework, str):
            framework = framework.strip() or None
        else:
            framework = None

        row: Dict[str, Any] = {
            "document_id": doc_id,
            "ingest_path": resolved,
            "tier": doc.get("tier"),
            "status": "pending",
            "chunks": 0,
        }

        if not os.path.isfile(resolved):
            row["status"] = "missing_file"
            results.append(row)
            first = False
            continue

        if dry_run:
            row["status"] = "dry_run"
            results.append(row)
            first = False
            continue

        use_reset = reset and first
        try:
            kwargs: Dict[str, Any] = {
                "file_path": resolved,
                "store_dir": store_dir,
                "collection_name": collection_name,
                "category": category,
                "jurisdiction": jurisdiction,
                "document_id": doc_id or None,
                "framework": framework,
                "reset": use_reset,
            }
            if embedding_model_name:
                kwargs["embedding_model_name"] = embedding_model_name
            n_chunks = ingest_policy_file(**kwargs)
            doc["ingested_at"] = now_iso
            row["status"] = "ok"
            row["chunks"] = n_chunks
        except Exception as exc:  # noqa: BLE001 — collect per-document failures
            row["status"] = "error"
            row["error"] = str(exc)
        results.append(row)
        first = False

    if not dry_run and any(r.get("status") == "ok" for r in results):
        data["updated"] = now_iso
        save_corpus_manifest(manifest_path, data)

    ok = sum(1 for r in results if r["status"] == "ok")
    missing = sum(1 for r in results if r["status"] == "missing_file")
    errors = sum(1 for r in results if r["status"] == "error")

    return {
        "manifest": os.path.abspath(manifest_path),
        "store": os.path.abspath(store_dir),
        "dry_run": dry_run,
        "ingested": ok,
        "missing_file": missing,
        "errors": errors,
        "results": results,
    }
