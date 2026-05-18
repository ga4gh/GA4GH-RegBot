from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from src.regbot.config import (
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    chromadb_settings,
)
from src.regbot.embeddings import load_sentence_transformer
from src.regbot.fusion import reciprocal_rank_fusion
from src.regbot.ingestion import read_manifest
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

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = load_sentence_transformer(self.embedding_model_name)
        return self._model

    def is_ready(self) -> bool:
        self._ensure_loaded()
        return self._collection is not None and bool(self._by_id)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        category: Optional[str] = None,
        semantic_candidates: int = 24,
        bm25_candidates: int = 24,
    ) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        if not query.strip() or self._collection is None or not self._by_id:
            return []

        def passes_filter(cid: str) -> bool:
            if not category:
                return True
            meta = self._by_id.get(cid, {}).get("metadata") or {}
            return str(meta.get("category", "")).lower() == category.lower()

        q_emb = self.model.encode([query], normalize_embeddings=True).tolist()[0]
        sem = self._collection.query(
            query_embeddings=[q_emb],
            n_results=min(semantic_candidates, len(self._by_id)),
            include=["documents", "metadatas", "distances"],
        )
        ids_raw = sem.get("ids")
        sem_ids: List[str] = list(ids_raw[0]) if ids_raw else []
        sem_ids = [i for i in sem_ids if passes_filter(i)]

        bm25_ids: List[str] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokenize(query))
            order = sorted(
                range(len(scores)),
                key=lambda i: scores[i],
                reverse=True,
            )
            for idx in order[:bm25_candidates]:
                cid = self._bm25_ids[idx]
                if passes_filter(cid):
                    bm25_ids.append(cid)

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
