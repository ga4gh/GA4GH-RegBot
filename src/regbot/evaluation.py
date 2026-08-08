"""
Retrieval benchmark for the GSoC Phase 2 gold set (see docs/DESIGN.md §4.2).

Gold labels are stored as *anchors* (``document_id`` + ``contains`` / ``page``), not raw
chunk ids: chunk ids embed a hash of the ingest path, so a literal id recorded on one
machine will not resolve on another. Anchors are resolved against the live store manifest
at evaluation time, which keeps the gold set portable across re-ingests and contributors.

Metrics reported per query and macro-averaged over the set:

``recall@k``     fraction of gold chunks present in the top-k results (primary metric)
``precision@k``  fraction of *returned* results that are gold (denominator is the number
                 actually returned, not k, so a small corpus is not penalised for
                 returning fewer than k candidates; ``returned`` is recorded per query)
``mrr@k``        reciprocal rank of the first gold chunk within the top-k, else 0
``hit@k``        1 when at least one gold chunk appears in the top-k
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml

from src.regbot.types import provision_keys

DEFAULT_KS: Tuple[int, ...] = (1, 3, 5, 8)

# Signature of a retrieval callable: (query, top_k, jurisdiction) -> chunk records.
RetrieveFn = Callable[[str, int, Optional[List[str]]], List[Dict[str, Any]]]


def _normalize_ws(text: str) -> str:
    return " ".join(str(text).split())


def load_gold_set(path: str) -> Dict[str, Any]:
    """Load and structurally validate a gold-set YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Gold set must be a mapping: {path}")
    queries = data.get("queries")
    if queries is None:
        data["queries"] = []
    elif not isinstance(queries, list):
        raise ValueError(f"'queries' must be a list in {path}")
    for i, q in enumerate(data["queries"]):
        if not isinstance(q, dict):
            raise ValueError(f"queries[{i}] must be a mapping in {path}")
        if not str(q.get("query") or "").strip():
            raise ValueError(f"queries[{i}] is missing a non-empty 'query' in {path}")
        relevant = q.get("relevant")
        if relevant is not None and not isinstance(relevant, list):
            raise ValueError(f"queries[{i}].relevant must be a list in {path}")
    return data


def chunk_matches_anchor(chunk: Dict[str, Any], anchor: Dict[str, Any]) -> bool:
    """True when every constraint present in ``anchor`` holds for ``chunk``."""
    meta = chunk.get("metadata") or {}

    want_id = anchor.get("chunk_id")
    if want_id and str(chunk.get("id") or "") != str(want_id):
        return False

    want_doc = anchor.get("document_id")
    if want_doc and str(meta.get("document_id") or "") != str(want_doc):
        return False

    want_source = anchor.get("source")
    if want_source and str(meta.get("source") or "") != str(want_source):
        return False

    want_page = anchor.get("page")
    if want_page is not None and int(meta.get("page", -1)) != int(want_page):
        return False

    contains = anchor.get("contains")
    if contains:
        haystack = _normalize_ws(str(chunk.get("text") or "")).lower()
        needle = _normalize_ws(str(contains)).lower()
        if needle not in haystack:
            return False

    return True


def resolve_anchors(
    anchors: Optional[Iterable[Dict[str, Any]]],
    chunks: Sequence[Dict[str, Any]],
) -> Tuple[Set[str], List[Dict[str, Any]]]:
    """
    Expand gold anchors into concrete chunk ids against the current store manifest.

    Returns ``(chunk_ids, unresolved_anchors)``. An anchor matching nothing is reported
    rather than dropped, so a stale gold set fails loudly instead of inflating recall.
    """
    resolved: Set[str] = set()
    unresolved: List[Dict[str, Any]] = []
    for anchor in anchors or []:
        if not isinstance(anchor, dict):
            continue
        hits = [str(c["id"]) for c in chunks if c.get("id") and chunk_matches_anchor(c, anchor)]
        if hits:
            resolved.update(hits)
        else:
            unresolved.append(dict(anchor))
    return resolved, unresolved


def _round(value: float) -> float:
    return round(float(value), 4)


def score_provisions(
    ranked_chunks: Sequence[Dict[str, Any]],
    gold_chunks: Sequence[Dict[str, Any]],
    ks: Sequence[int],
) -> Dict[str, float]:
    """Recall over provisions rather than chunks — stable across chunking schemes."""
    gold: Set[str] = set()
    for c in gold_chunks:
        gold |= provision_keys(c)

    scores: Dict[str, float] = {}
    for k in ks:
        found: Set[str] = set()
        for c in ranked_chunks[:k]:
            found |= provision_keys(c)
        hit = found & gold
        scores[f"provision_recall@{k}"] = _round(len(hit) / len(gold)) if gold else 0.0
    return scores


def score_ranking(
    ranked_ids: Sequence[str],
    gold_ids: Set[str],
    ks: Sequence[int],
) -> Dict[str, float]:
    """Compute recall@k / precision@k / mrr@k / hit@k for one ranked result list."""
    scores: Dict[str, float] = {}
    for k in ks:
        top = list(ranked_ids[:k])
        relevant_found = [cid for cid in top if cid in gold_ids]

        recall = len(relevant_found) / len(gold_ids) if gold_ids else 0.0
        precision = len(relevant_found) / len(top) if top else 0.0

        rr = 0.0
        for rank, cid in enumerate(top, start=1):
            if cid in gold_ids:
                rr = 1.0 / rank
                break

        scores[f"recall@{k}"] = _round(recall)
        scores[f"precision@{k}"] = _round(precision)
        scores[f"mrr@{k}"] = _round(rr)
        scores[f"hit@{k}"] = 1.0 if relevant_found else 0.0
    return scores


def evaluate_gold_set(
    gold: Dict[str, Any],
    chunks: Sequence[Dict[str, Any]],
    retrieve_fn: RetrieveFn,
    *,
    ks: Sequence[int] = DEFAULT_KS,
    label: str = "baseline",
) -> Dict[str, Any]:
    """
    Run every gold query through ``retrieve_fn`` and score the rankings.

    ``retrieve_fn`` is injected so the harness can be unit-tested with a stub retriever
    and reused for parameter sweeps without touching the CLI.
    """
    ks = tuple(sorted({int(k) for k in ks if int(k) > 0}))
    if not ks:
        ks = DEFAULT_KS
    max_k = max(ks)

    per_query: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for entry in gold.get("queries") or []:
        query = str(entry.get("query") or "").strip()
        query_id = str(entry.get("query_id") or query[:40])
        jurisdiction = entry.get("jurisdiction") or None
        if isinstance(jurisdiction, str):
            jurisdiction = [jurisdiction]
        jurisdiction_list = [str(j) for j in jurisdiction] if jurisdiction else None

        gold_ids, unresolved = resolve_anchors(entry.get("relevant"), chunks)

        if not gold_ids:
            skipped.append(
                {
                    "query_id": query_id,
                    "query": query,
                    "reason": "no_gold_anchor_resolved",
                    "unresolved_anchors": unresolved,
                }
            )
            continue

        hits = retrieve_fn(query, max_k, jurisdiction_list)
        ranked_ids = [str(h.get("id")) for h in hits if h.get("id")]

        gold_chunks = [c for c in chunks if str(c.get("id")) in gold_ids]
        gold_provisions: Set[str] = set()
        for c in gold_chunks:
            gold_provisions |= provision_keys(c)

        scores = score_ranking(ranked_ids, gold_ids, ks)
        scores.update(score_provisions(hits, gold_chunks, ks))

        row: Dict[str, Any] = {
            "query_id": query_id,
            "query": query,
            "jurisdiction": jurisdiction_list,
            "gold_count": len(gold_ids),
            "gold_provisions": sorted(gold_provisions),
            "returned": len(ranked_ids),
            "top_chunk_ids": ranked_ids[:max_k],
            "scores": scores,
        }
        if unresolved:
            row["unresolved_anchors"] = unresolved
        per_query.append(row)

    aggregate: Dict[str, float] = {}
    if per_query:
        metric_names = list(per_query[0]["scores"].keys())
        for name in metric_names:
            aggregate[name] = _round(
                sum(float(r["scores"][name]) for r in per_query) / len(per_query)
            )

    return {
        "label": label,
        "gold_set_version": str(gold.get("version") or ""),
        "ks": list(ks),
        "query_count": len(per_query),
        "skipped_count": len(skipped),
        "aggregate": aggregate,
        "per_query": per_query,
        "skipped": skipped,
    }


def format_markdown_report(result: Dict[str, Any]) -> str:
    """Render a benchmark run as Markdown for docs/eval_results.md."""
    ks = result.get("ks") or list(DEFAULT_KS)
    agg = result.get("aggregate") or {}
    lines: List[str] = []

    lines.append(f"### Run: `{result.get('label', 'baseline')}`")
    lines.append("")
    lines.append(
        f"Gold set version `{result.get('gold_set_version') or 'n/a'}` · "
        f"{result.get('query_count', 0)} scored queries · "
        f"{result.get('skipped_count', 0)} skipped"
    )
    lines.append("")
    lines.append("| k | Recall@k | Precision@k | MRR@k | Hit@k |")
    lines.append("|---|----------|-------------|-------|-------|")
    for k in ks:
        lines.append(
            f"| {k} "
            f"| {agg.get(f'recall@{k}', 0):.3f} "
            f"| {agg.get(f'precision@{k}', 0):.3f} "
            f"| {agg.get(f'mrr@{k}', 0):.3f} "
            f"| {agg.get(f'hit@{k}', 0):.3f} |"
        )
    lines.append("")

    primary = max(ks)
    lines.append(f"Per-query recall@{primary}:")
    lines.append("")
    lines.append("| Query | Jurisdiction | Gold | Returned | Recall | MRR |")
    lines.append("|-------|--------------|------|----------|--------|-----|")
    for row in result.get("per_query") or []:
        scores = row.get("scores") or {}
        jur = ", ".join(row.get("jurisdiction") or []) or "—"
        lines.append(
            f"| {row.get('query_id')} "
            f"| {jur} "
            f"| {row.get('gold_count')} "
            f"| {row.get('returned')} "
            f"| {scores.get(f'recall@{primary}', 0):.3f} "
            f"| {scores.get(f'mrr@{primary}', 0):.3f} |"
        )

    skipped = result.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append("**Skipped (no gold anchor resolved against the current store):**")
        lines.append("")
        for row in skipped:
            lines.append(f"- `{row.get('query_id')}` — {row.get('reason')}")

    lines.append("")
    return "\n".join(lines)


def write_markdown_report(path: str, result: Dict[str, Any], *, header: str = "") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    body = format_markdown_report(result)
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(header.rstrip() + "\n\n")
        f.write(body)


def dumps(result: Dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)
