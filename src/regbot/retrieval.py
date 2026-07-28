from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from rank_bm25 import BM25Okapi

from src.regbot.config import (
    BM25_CANDIDATES,
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    SEMANTIC_CANDIDATES,
    chromadb_settings,
)
from src.regbot.embeddings import load_sentence_transformer
from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.ingestion import read_manifest
from src.regbot.jurisdiction import jurisdiction_matches, jurisdictions_in_manifest
from src.regbot.text_utils import tokenize


class HybridRetriever:
    def __init__(
        self,
        store_dir: str,
        *,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.store_dir = store_dir
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self._model: Any = None
        self._collection: Any = None
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_ids: List[str] = []
        self._embeddings: Any = None
        self._embedding_ids: List[str] = []

    def _ensure_loaded(self) -> None:
        if self._collection is not None:
            return
        import chromadb  # lazy: keeps lightweight imports working on odd Python combos

        chroma_path = os.path.join(self.store_dir, CHROMA_SUBDIR)
        if not os.path.isdir(chroma_path):
            return
        client = chromadb.PersistentClient(path=chroma_path, settings=chromadb_settings())
        try:
            self._collection = client.get_collection(self.collection_name)
        except Exception:
            self._collection = None
            return

        chunks = read_manifest(self.store_dir)
        self._by_id = {c["id"]: c for c in chunks}
        self._bm25_ids = [c["id"] for c in chunks]
        tokenized = [tokenize(self._by_id[i]["text"]) for i in self._bm25_ids]
        if tokenized:
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None

        self._load_embeddings()

    def _load_embeddings(self) -> None:
        """
        Pull every stored embedding into memory for exact cosine search.

        Chroma's HNSW index is *approximate*: the same query embedding against the same
        collection returns different tail neighbours across processes, which jitters the
        candidate-pool boundary and propagates into the fused top-k. That makes benchmark
        numbers irreproducible and a `--min-recall` CI gate flaky.

        Exact search removes that class of problem. It costs nothing architecturally: the
        retriever already holds every chunk's full text in memory for BM25, so memory was
        already proportional to corpus size. At the current corpus (128 chunks x 384 dims)
        this is a few hundred kilobytes.
        """
        if self._collection is None:
            return
        try:
            import numpy as np

            payload = self._collection.get(include=["embeddings"])
            ids = list(payload.get("ids") or [])
            vectors = payload.get("embeddings")
            if not ids or vectors is None or len(vectors) == 0:
                return
            matrix = np.asarray(vectors, dtype=float)
            # Ingest normalizes embeddings, but re-normalize defensively so cosine == dot.
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._embeddings = matrix / norms
            self._embedding_ids = [str(i) for i in ids]
        except Exception:
            # Fall back to Chroma's ANN query; retrieval still works, just not bit-reproducible.
            self._embeddings = None
            self._embedding_ids = []

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = load_sentence_transformer(self.embedding_model_name)
        return self._model

    def is_ready(self) -> bool:
        self._ensure_loaded()
        return self._collection is not None and bool(self._by_id)

    def list_jurisdictions(self) -> List[str]:
        """Jurisdiction codes present in the store manifest."""
        self._ensure_loaded()
        return jurisdictions_in_manifest(list(self._by_id.values()))

    def _dense_candidates(
        self,
        query_embedding: List[float],
        limit: int,
        allowed: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        Top-``limit`` chunk ids by cosine similarity, ranked deterministically.

        ``allowed`` restricts the candidate universe *before* the top-``limit`` cut, so a
        scoped query fills its pool with in-scope chunks. Selecting globally and filtering
        afterwards would leave a narrow scope with almost nothing to fuse.

        Ties break on chunk id so equal-scoring chunks always order the same way; without
        that, ordering would depend on dict insertion order and stay irreproducible even
        with exact scores.
        """
        if self._embeddings is None or not self._embedding_ids:
            # Approximate fallback when embeddings could not be loaded. Over-fetch, then
            # filter, since the ANN index cannot be restricted up front.
            if self._collection is None:
                return []
            want = limit if allowed is None else min(limit * 8, max(1, len(self._by_id)))
            sem = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(want, max(1, len(self._by_id))),
                include=["documents", "metadatas", "distances"],
            )
            ids_raw = sem.get("ids")
            ids = list(ids_raw[0]) if ids_raw else []
            if allowed is not None:
                ids = [i for i in ids if i in allowed]
            return ids[:limit]

        import numpy as np

        q = np.asarray(query_embedding, dtype=float)
        norm = float(np.linalg.norm(q))
        if norm:
            q = q / norm
        sims = self._embeddings @ q
        pairs: Iterable[Tuple[str, float]] = zip(self._embedding_ids, sims.tolist())
        if allowed is not None:
            pairs = ((cid, s) for cid, s in pairs if cid in allowed)
        scored = sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
        return [cid for cid, _ in scored[:limit]]

    def _allowed_ids(
        self,
        *,
        category: Optional[str] = None,
        jurisdiction: Optional[List[str]] = None,
        framework: Optional[List[str]] = None,
    ) -> Optional[Set[str]]:
        """
        Chunk ids satisfying every active filter, or ``None`` when nothing is scoped.

        ``None`` means "no restriction" and lets the caller skip the membership test
        entirely — distinct from an empty set, which means the scope matched nothing.
        """
        if not category and not jurisdiction and not framework:
            return None

        wanted_frameworks = (
            {str(f).strip().upper() for f in framework if str(f).strip()} if framework else None
        )
        allowed: Set[str] = set()
        for cid, rec in self._by_id.items():
            meta = rec.get("metadata") or {}
            if category and str(meta.get("category", "")).lower() != category.lower():
                continue
            if jurisdiction and not jurisdiction_matches(meta, jurisdiction):
                continue
            if wanted_frameworks:
                if str(meta.get("framework", "")).strip().upper() not in wanted_frameworks:
                    continue
            allowed.add(cid)
        return allowed

    def list_frameworks(self) -> List[str]:
        """Framework labels present in the store manifest (GA4GH, GDPR, REWS, national…)."""
        self._ensure_loaded()
        found = {
            str((r.get("metadata") or {}).get("framework", "")).strip()
            for r in self._by_id.values()
        }
        return sorted(f for f in found if f)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        category: Optional[str] = None,
        jurisdiction: Optional[List[str]] = None,
        framework: Optional[List[str]] = None,
        semantic_candidates: Optional[int] = None,
        bm25_candidates: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        semantic_candidates = (
            SEMANTIC_CANDIDATES if semantic_candidates is None else int(semantic_candidates)
        )
        bm25_candidates = BM25_CANDIDATES if bm25_candidates is None else int(bm25_candidates)
        self._ensure_loaded()
        if not query.strip() or self._collection is None or not self._by_id:
            return []

        allowed = self._allowed_ids(
            category=category, jurisdiction=jurisdiction, framework=framework
        )
        if allowed is not None and not allowed:
            return []

        q_emb = self.model.encode([query], normalize_embeddings=True).tolist()[0]
        sem_ids = self._dense_candidates(q_emb, semantic_candidates, allowed)

        bm25_ids: List[str] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokenize(query))
            order = sorted(
                range(len(scores)),
                key=lambda i: (-scores[i], self._bm25_ids[i]),
            )
            for idx in order:
                cid = self._bm25_ids[idx]
                if allowed is not None and cid not in allowed:
                    continue
                bm25_ids.append(cid)
                if len(bm25_ids) >= bm25_candidates:
                    break

        fused = reciprocal_rank_fusion([sem_ids, bm25_ids], top_n=max(top_k * 3, top_k))

        out: List[Dict[str, Any]] = []
        for cid in fused:
            if cid not in self._by_id:
                continue
            rec = self._by_id[cid]
            out.append(
                {
                    "id": rec["id"],
                    "text": rec["text"],
                    "metadata": dict(rec.get("metadata") or {}),
                }
            )
            if len(out) >= top_k:
                break
        return out
