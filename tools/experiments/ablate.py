"""
Retrieval ablations and baselines with paired significance tests.

The production retriever (``src/regbot/retrieval.py``) accumulated its design one measured
change at a time (docs/eval_results.md §3-§4k). This script re-runs every such decision as
a controlled ablation against one fixed corpus snapshot and gold set, adds stronger
embedding and re-ranking baselines, and reports per-query paired tests so a difference is
only called an improvement when it survives resampling.

It reads the store's ``manifest.json`` (chunk text + metadata) and computes embeddings
itself, so it does not need Chroma. Chunk embeddings are cached per model under
``$REGBOT_EXPERIMENT_CACHE`` (default ``~/.cache/regbot/embeddings``), keyed by a hash of
the exact texts embedded, so a corpus rebuild never reuses stale vectors.

    python tools/experiments/ablate.py --suite core
    python tools/experiments/ablate.py --suite models --out docs/benchmarks/ablations.json
    python tools/experiments/ablate.py --list

The ``baseline`` configuration must reproduce ``python -m src.main benchmark`` exactly; the
script prints both so any drift between this reimplementation and production is visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402
from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402
from src.regbot.evaluation import evaluate_gold_set, load_gold_set  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402
from src.regbot.jurisdiction import jurisdiction_matches  # noqa: E402
from src.regbot.significance import (  # noqa: E402
    bootstrap_ci,
    holm_adjust,
    paired_bootstrap_ci,
    paired_permutation_p,
)
from src.regbot.text_utils import tokenize  # noqa: E402
from src.regbot.types import provision_keys  # noqa: E402

MINILM = "sentence-transformers/all-MiniLM-L6-v2"

# Query / document prompts each model was trained with. Using a model without its prompt
# understates it, which would make the baseline comparison unfair.
MODEL_PROMPTS: Dict[str, Tuple[str, str]] = {
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-base-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "nomic-ai/nomic-embed-text-v1.5": ("search_query: ", "search_document: "),
    "intfloat/e5-base-v2": ("query: ", "passage: "),
    "Qwen/Qwen3-Embedding-0.6B": (
        "Instruct: Given a question about genomic data governance, retrieve the legal or "
        "policy provisions that answer it\nQuery: ",
        "",
    ),
}
TRUST_REMOTE_CODE = {"nomic-ai/nomic-embed-text-v1.5"}


@dataclass(frozen=True)
class Config:
    """One retriever variant. Defaults equal the production configuration."""

    name: str
    embedder: Optional[str] = MINILM  # None disables the dense channel
    lexical: bool = True  # False disables BM25
    fusion: str = "max"
    rrf_k: int = 60
    sem: int = 12
    bm25: int = 48
    cap: int = 2
    fold_plural: bool = True
    scoped_idf: bool = True
    contextual: bool = False  # prefix document title + section to the indexed text
    reranker: Optional[str] = None
    rerank_depth: int = 40
    note: str = ""


def _baseline(**kw: Any) -> Config:
    return replace(Config(name="baseline"), **kw)


SUITES: Dict[str, List[Config]] = {
    # Every production design decision, removed one at a time.
    "core": [
        _baseline(note="production configuration"),
        _baseline(name="bm25_only", embedder=None, note="lexical channel only"),
        _baseline(name="dense_only", lexical=False, sem=48, note="dense channel only"),
        _baseline(name="fusion_sum", fusion="sum", note="classic additive RRF"),
        _baseline(name="no_plural_fold", fold_plural=False, note="raw tokens for BM25"),
        _baseline(name="global_idf", scoped_idf=False, note="BM25 stats over whole corpus"),
        _baseline(name="no_provision_cap", cap=0, note="no per-provision fragment cap"),
        _baseline(name="cap_1", cap=1, note="one fragment per provision"),
        _baseline(name="pools_24_24", sem=24, bm25=24, note="original pool sizes"),
        _baseline(name="contextual", contextual=True, note="title+section prefix indexed"),
    ],
    # Stronger dense encoders, each in the production hybrid.
    "models": [
        _baseline(note="MiniLM-L6 (production)"),
        _baseline(name="bge_small", embedder="BAAI/bge-small-en-v1.5"),
        _baseline(name="bge_base", embedder="BAAI/bge-base-en-v1.5"),
        _baseline(name="bge_m3", embedder="BAAI/bge-m3"),
        _baseline(name="qwen3_0.6b", embedder="Qwen/Qwen3-Embedding-0.6B"),
        _baseline(name="bge_m3_dense_only", embedder="BAAI/bge-m3", lexical=False, sem=48),
        _baseline(
            name="qwen3_dense_only", embedder="Qwen/Qwen3-Embedding-0.6B", lexical=False, sem=48
        ),
        _baseline(name="bge_m3_sum", embedder="BAAI/bge-m3", fusion="sum"),
        _baseline(name="qwen3_sum", embedder="Qwen/Qwen3-Embedding-0.6B", fusion="sum"),
    ],
    # Second-stage cross-encoders over the fused candidate list.
    "rerank": [
        _baseline(note="no reranker"),
        _baseline(name="rr_msmarco_minilm", reranker="cross-encoder/ms-marco-MiniLM-L6-v2"),
        _baseline(name="rr_bge_v2_m3", reranker="BAAI/bge-reranker-v2-m3"),
        _baseline(
            name="qwen3_rr_bge_v2_m3",
            embedder="Qwen/Qwen3-Embedding-0.6B",
            reranker="BAAI/bge-reranker-v2-m3",
        ),
    ],
}

PRIMARY_METRICS = ("provision_recall@5", "provision_recall@8", "mrr@8", "hit@8")


# --------------------------------------------------------------------------- tokenization


def tokenize_no_fold(text: str) -> List[str]:
    """``tokenize`` without plural folding (CJK bigrams unchanged)."""
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    for run in re.findall(r"[㐀-䶿一-鿿぀-ヿ가-힯]+", lowered):
        tokens.extend([run] if len(run) == 1 else [run[i : i + 2] for i in range(len(run) - 1)])
    return tokens


# --------------------------------------------------------------------------- embeddings


def _device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


class Encoders:
    """Lazy model loading and on-disk chunk-embedding cache."""

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir
        self._models: Dict[str, Any] = {}
        self._rerankers: Dict[str, Any] = {}

    def model(self, name: str) -> Any:
        if name not in self._models:
            from sentence_transformers import SentenceTransformer
            from src.regbot.embeddings import load_sentence_transformer

            if name in TRUST_REMOTE_CODE:
                self._models[name] = SentenceTransformer(
                    name, trust_remote_code=True, device=_device()
                )
            else:
                m = load_sentence_transformer(name)
                m.to(_device())
                self._models[name] = m
        return self._models[name]

    def reranker(self, name: str) -> Any:
        if name not in self._rerankers:
            from sentence_transformers import CrossEncoder

            self._rerankers[name] = CrossEncoder(name, device=_device(), max_length=512)
        return self._rerankers[name]

    def encode_docs(self, name: str, texts: Sequence[str]) -> np.ndarray:
        doc_prompt = MODEL_PROMPTS.get(name, ("", ""))[1]
        digest = hashlib.sha256()
        digest.update(name.encode())
        digest.update(doc_prompt.encode())
        for t in texts:
            digest.update(b"\x00")
            digest.update(t.encode("utf-8"))
        key = digest.hexdigest()[:24]
        os.makedirs(self.cache_dir, exist_ok=True)
        path = os.path.join(self.cache_dir, f"{name.replace('/', '__')}-{key}.npy")
        if os.path.exists(path):
            return np.load(path)
        t0 = time.time()
        vecs = self.model(name).encode(
            [doc_prompt + t for t in texts],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        vecs = np.asarray(vecs, dtype=np.float32)
        np.save(path, vecs)
        print(
            f"  encoded {len(texts)} chunks with {name} in {time.time() - t0:.0f}s", file=sys.stderr
        )
        return vecs

    def encode_query(self, name: str, query: str) -> np.ndarray:
        prompt = MODEL_PROMPTS.get(name, ("", ""))[0]
        v = self.model(name).encode(
            [prompt + query], normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(v[0], dtype=np.float64)


# --------------------------------------------------------------------------- retriever


def _indexed_text(chunk: Dict[str, Any], titles: Dict[str, str], contextual: bool) -> str:
    text = str(chunk.get("text") or "")
    if not contextual:
        return text
    meta = chunk.get("metadata") or {}
    title = titles.get(str(meta.get("document_id") or ""), "")
    section = str(meta.get("section") or "").strip()
    head = " — ".join(p for p in (title, section) if p)
    return f"{head}\n{text}" if head else text


class ExperimentRetriever:
    """A re-implementation of ``HybridRetriever.retrieve`` with every decision exposed."""

    def __init__(
        self,
        chunks: List[Dict[str, Any]],
        cfg: Config,
        enc: Encoders,
        titles: Dict[str, str],
        allowed_docs: Optional[Set[str]] = None,
    ) -> None:
        self.cfg = cfg
        # Restricting by document_id here, rather than passing a subset of chunks, keeps the
        # embedding cache valid: the cache is keyed on the full list of indexed texts.
        self.allowed_docs = allowed_docs
        self.enc = enc
        self.chunks = chunks
        self.by_id = {c["id"]: c for c in chunks}
        self.ids = [c["id"] for c in chunks]
        self.texts = [_indexed_text(c, titles, cfg.contextual) for c in chunks]
        self.raw_texts = {c["id"]: str(c.get("text") or "") for c in chunks}
        tok = tokenize if cfg.fold_plural else tokenize_no_fold
        self.tok = tok
        self.tokens = {i: tok(t) for i, t in zip(self.ids, self.texts)}
        self.bm25 = BM25Okapi([self.tokens[i] for i in self.ids]) if cfg.lexical else None
        self.emb = (
            enc.encode_docs(cfg.embedder, self.texts).astype(np.float64) if cfg.embedder else None
        )
        self._scoped_bm25: Dict[Tuple[str, ...], Tuple[List[str], BM25Okapi]] = {}

    def _allowed(self, jurisdiction: Optional[List[str]]) -> Optional[Set[str]]:
        if not jurisdiction and self.allowed_docs is None:
            return None
        return {
            c["id"]
            for c in self.chunks
            if (not jurisdiction or jurisdiction_matches(c.get("metadata") or {}, jurisdiction))
            and (
                self.allowed_docs is None
                or str((c.get("metadata") or {}).get("document_id")) in self.allowed_docs
            )
        }

    def _dense(self, query: str, limit: int, allowed: Optional[Set[str]]) -> List[str]:
        if self.emb is None or self.cfg.embedder is None or limit <= 0:
            return []
        q = self.enc.encode_query(self.cfg.embedder, query)
        sims = np.einsum("ij,j->i", self.emb, q, optimize=True).tolist()
        pairs: Iterable[Tuple[str, float]] = zip(self.ids, sims)
        if allowed is not None:
            pairs = ((i, s) for i, s in pairs if i in allowed)
        ranked = sorted(pairs, key=lambda p: (-p[1], p[0]))
        return [i for i, _ in ranked[:limit]]

    def _lexical(
        self, query: str, limit: int, allowed: Optional[Set[str]], key: Tuple[str, ...]
    ) -> List[str]:
        if self.bm25 is None or limit <= 0:
            return []
        qt = self.tok(query)
        if allowed is None:
            ids, bm = self.ids, self.bm25
        elif self.cfg.scoped_idf:
            if key not in self._scoped_bm25:
                ids_s = [i for i in self.ids if i in allowed]
                self._scoped_bm25[key] = (ids_s, BM25Okapi([self.tokens[i] for i in ids_s]))
            ids, bm = self._scoped_bm25[key]
        else:
            all_scores = self.bm25.get_scores(qt)
            pairs = [(i, s) for i, s in zip(self.ids, all_scores) if i in allowed]
            pairs.sort(key=lambda p: (-p[1], p[0]))
            return [i for i, _ in pairs[:limit]]
        scores = bm.get_scores(qt)
        order = sorted(range(len(ids)), key=lambda j: (-scores[j], ids[j]))
        return [ids[j] for j in order[:limit]]

    def _fuse(self, lists: Sequence[Sequence[str]], top_n: int) -> List[str]:
        contrib: Dict[str, List[float]] = defaultdict(list)
        for ids in lists:
            for rank, cid in enumerate(ids):
                contrib[cid].append(1.0 / (self.cfg.rrf_k + rank + 1))
        comb = max if self.cfg.fusion == "max" else sum
        scores = {c: comb(v) for c, v in contrib.items()}
        return sorted(scores, key=lambda c: (-scores[c], c))[:top_n]

    def retrieve(
        self, query: str, top_k: int, jurisdiction: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        cfg = self.cfg
        allowed = self._allowed(jurisdiction)
        key = tuple(sorted(jurisdiction or []))
        sem_ids = self._dense(query, cfg.sem, allowed)
        lex_ids = self._lexical(query, cfg.bm25, allowed, key)
        headroom = 6 if cfg.cap > 0 else 3
        depth = max(top_k * headroom, top_k, cfg.rerank_depth if cfg.reranker else 0)
        fused = self._fuse([sem_ids, lex_ids], depth)
        if cfg.reranker:
            head = fused[: cfg.rerank_depth]
            ce = self.enc.reranker(cfg.reranker)
            scores = ce.predict([(query, self.raw_texts[c]) for c in head], batch_size=16)
            order = sorted(range(len(head)), key=lambda j: (-float(scores[j]), head[j]))
            fused = [head[j] for j in order] + fused[cfg.rerank_depth :]
        out: List[Dict[str, Any]] = []
        used: Dict[str, int] = {}
        for cid in fused:
            rec = self.by_id[cid]
            keys = provision_keys(rec) if cfg.cap > 0 else set()
            if cfg.cap > 0 and any(used.get(k, 0) >= cfg.cap for k in keys):
                continue
            for k in keys:
                used[k] = used.get(k, 0) + 1
            out.append(rec)
            if len(out) >= top_k:
                break
        return out


# --------------------------------------------------------------------------- reporting


def provision_mrr(result: Dict[str, Any], by_id: Dict[str, Dict[str, Any]], k: int) -> List[float]:
    """Reciprocal rank of the first result belonging to any gold provision."""
    out = []
    for row in result["per_query"]:
        gold = set(row["gold_provisions"])
        rr = 0.0
        for rank, cid in enumerate(row["top_chunk_ids"][:k], start=1):
            if provision_keys(by_id[cid]) & gold:
                rr = 1.0 / rank
                break
        out.append(rr)
    return out


def per_query(result: Dict[str, Any], metric: str) -> List[float]:
    return [float(r["scores"][metric]) for r in result["per_query"]]


def summarize(
    runs: Dict[str, Dict[str, Any]],
    baseline: str,
    metrics: Sequence[str],
) -> Dict[str, Any]:
    base = runs[baseline]
    table: Dict[str, Any] = {}
    raw_p: Dict[str, float] = {}
    for name, res in runs.items():
        row: Dict[str, Any] = {}
        for m in metrics:
            vals = res["vectors"][m]
            lo, hi = bootstrap_ci(vals)
            cell: Dict[str, Any] = {
                "mean": round(sum(vals) / len(vals), 4),
                "ci95": [round(lo, 4), round(hi, 4)],
            }
            if name != baseline:
                b = base["vectors"][m]
                dlo, dhi = paired_bootstrap_ci(vals, b)
                p = paired_permutation_p(vals, b)
                cell.update(
                    {
                        "delta": round(cell["mean"] - sum(b) / len(b), 4),
                        "delta_ci95": [round(dlo, 4), round(dhi, 4)],
                        "p": round(p, 4),
                        "wins": sum(1 for x, y in zip(vals, b) if x > y + 1e-12),
                        "losses": sum(1 for x, y in zip(vals, b) if x < y - 1e-12),
                    }
                )
                raw_p[f"{name}|{m}"] = p
            row[m] = cell
        table[name] = row
    # Holm within each metric: the family is "every variant compared on this metric".
    for m in metrics:
        family = {k: v for k, v in raw_p.items() if k.endswith(f"|{m}")}
        for key, adj in holm_adjust(family).items():
            table[key.split("|", 1)[0]][m]["p_holm"] = round(adj, 4)
    return table


def render_markdown(
    table: Dict[str, Any], configs: Dict[str, Config], metrics: Sequence[str], n: int
) -> str:
    head = "| Config | " + " | ".join(metrics) + " |"
    sep = "|---|" + "---|" * len(metrics)
    lines = [
        f"n = {n} queries. Cells: mean [95% bootstrap CI]; Δ vs baseline with paired permutation p (raw, and Holm-adjusted across variants per metric); * = p_Holm < 0.05.",
        "",
        head,
        sep,
    ]
    for name, row in table.items():
        cells = []
        for m in metrics:
            c = row[m]
            s = f"{c['mean']:.3f} [{c['ci95'][0]:.2f}, {c['ci95'][1]:.2f}]"
            if "delta" in c:
                star = "*" if c.get("p_holm", 1) < 0.05 else ""
                s += (
                    f"<br>Δ {c['delta']:+.3f}{star} (p={c['p']:.3f}, "
                    f"p_Holm={c.get('p_holm', c['p']):.3f}, {c['wins']}↑/{c['losses']}↓)"
                )
            cells.append(s)
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")
    lines.append("")
    for name, cfg in configs.items():
        if cfg.note:
            lines.append(f"- `{name}`: {cfg.note}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--store", default=os.path.join(ROOT, "data", "regbot_store"))
    ap.add_argument("--gold", default=os.path.join(ROOT, "examples", "eval", "gold_ga4gh.yaml"))
    ap.add_argument("--corpus-manifest", default=os.path.join(ROOT, "docs", "corpus_manifest.yaml"))
    ap.add_argument("--suite", action="append", choices=sorted(SUITES), help="repeatable")
    ap.add_argument("--only", action="append", help="run only these config names")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", help="write full JSON results here")
    ap.add_argument("--markdown", help="write the summary table here")
    ap.add_argument(
        "--cache",
        default=os.environ.get(
            "REGBOT_EXPERIMENT_CACHE", os.path.expanduser("~/.cache/regbot/embeddings")
        ),
    )
    args = ap.parse_args(argv)

    suites = args.suite or ["core"]
    configs: Dict[str, Config] = {}
    for s in suites:
        for c in SUITES[s]:
            configs.setdefault(c.name, c)
    if args.only:
        configs = {k: v for k, v in configs.items() if k in set(args.only) or k == "baseline"}
    if args.list:
        for name, c in configs.items():
            print(name, json.dumps({k: v for k, v in asdict(c).items() if k != "name"}))
        return 0

    chunks = read_manifest(args.store)
    gold = load_gold_set(args.gold)
    titles = {
        d["document_id"]: d.get("title", "")
        for d in load_corpus_manifest(args.corpus_manifest).get("documents", [])
    }
    enc = Encoders(args.cache)
    by_id = {c["id"]: c for c in chunks}

    runs: Dict[str, Dict[str, Any]] = {}
    for name, cfg in configs.items():
        t0 = time.time()
        print(f"[{name}] building index", file=sys.stderr)
        r = ExperimentRetriever(chunks, cfg, enc, titles)
        res = evaluate_gold_set(gold, chunks, r.retrieve, label=name)
        if res["skipped_count"] or res["unresolved_anchor_count"]:
            print(f"[{name}] gold set does not fully resolve; aborting", file=sys.stderr)
            return 1
        vectors = {m: per_query(res, m) for m in res["aggregate"]}
        vectors["provision_mrr@8"] = provision_mrr(res, by_id, 8)
        runs[name] = {
            "config": asdict(cfg),
            "aggregate": res["aggregate"],
            "vectors": vectors,
            "per_query": [
                {"query_id": q["query_id"], "top": q["top_chunk_ids"]} for q in res["per_query"]
            ],
            "seconds": round(time.time() - t0, 1),
        }
        agg = res["aggregate"]
        print(
            f"[{name}] P-R@5={agg['provision_recall@5']:.4f} P-R@8={agg['provision_recall@8']:.4f} "
            f"MRR@8={agg['mrr@8']:.4f} ({runs[name]['seconds']}s)",
            file=sys.stderr,
        )

    metrics = list(PRIMARY_METRICS) + ["provision_mrr@8"]
    baseline = "baseline" if "baseline" in runs else next(iter(runs))
    table = summarize(runs, baseline, metrics)
    n = len(next(iter(runs.values()))["vectors"][metrics[0]])
    md = render_markdown(table, configs, metrics, n)
    print(md)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(md + "\n")
    if args.out:
        payload = {
            "gold_version": gold.get("version"),
            "chunks": len(chunks),
            "store_manifest_sha256": hashlib.sha256(
                open(os.path.join(args.store, "manifest.json"), "rb").read()
            ).hexdigest(),
            "summary": table,
            "runs": runs,
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
