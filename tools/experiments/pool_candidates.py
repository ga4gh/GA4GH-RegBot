"""
TREC-style candidate pooling for relevance adjudication.

The v0.9 gold set was written by reading the production retriever's own output, which
favours that retriever: stronger embedders score *lower* against it (docs/eval_results.md,
tools/experiments/ablate.py --suite models). Pooling removes that bias by judging the
union of the top-k lists of several heterogeneous systems, so a provision only one system
finds still gets a relevance judgment.

Two steps:

  pool     queries YAML -> adjudication sheet (one row per pooled provision, blank label)
  anchors  adjudicated sheet -> gold-set YAML in the existing anchor format

    python tools/experiments/pool_candidates.py pool --queries new_queries.yaml \
        --systems baseline,bm25_only,dense_only,fusion_sum,bge_base,contextual \
        --depth 10 --out pool.yaml
    # judge each candidate: label 2 = operative provision, 1 = related, 0 = not relevant
    python tools/experiments/pool_candidates.py anchors --pool pool.yaml --out gold_new.yaml

Candidates are grouped by *provision* (document + section), the unit the benchmark scores,
so an annotator judges each rule once rather than every overlapping fragment of it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import yaml  # noqa: E402
from ablate import SUITES, Encoders, ExperimentRetriever  # noqa: E402
from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402
from units import coarse_documents, judgment_units  # noqa: E402


def _all_configs() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for suite in SUITES.values():
        for c in suite:
            out.setdefault(c.name, c)
    return out


def _anchor_phrase(text: str, others: Sequence[str], words: int = 8) -> Optional[str]:
    """
    A short verbatim phrase from ``text`` that occurs in no chunk of ``others``.

    Gold anchors are ``document_id`` + ``contains``; the phrase must be specific enough to
    resolve to this provision only. Windows are tried from the start of the chunk so the
    anchor usually quotes the provision's opening words.
    """
    tokens = text.split()
    norm_others = [" ".join(o.split()).lower() for o in others]
    for n in (words, words + 4, words + 8):
        for i in range(0, max(1, len(tokens) - n + 1)):
            phrase = " ".join(tokens[i : i + n])
            if len(re.sub(r"[^A-Za-z㐀-鿿]", "", phrase)) < 20:
                continue
            low = phrase.lower()
            if not any(low in o for o in norm_others):
                return phrase
    return None


def crosswalk_cells(path: str) -> List[Dict[str, Any]]:
    """One pooling item per (aspect, jurisdiction) cell, carrying every normative phrasing."""
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    cells = []
    for a in spec.get("aspects") or []:
        for j in spec.get("jurisdictions") or []:
            cells.append(
                {
                    "query_id": f"{a['id']}-{j}",
                    "aspect": a["id"],
                    "aspect_label": a["label"],
                    "definition": " ".join(str(a.get("definition") or "").split()),
                    "jurisdiction": [j],
                    "queries": list(a.get("normative_queries") or []),
                }
            )
    return cells


def cmd_pool(args: argparse.Namespace) -> int:
    chunks = read_manifest(args.store)
    titles = {
        d["document_id"]: d.get("title", "")
        for d in load_corpus_manifest(args.corpus_manifest).get("documents", [])
    }
    configs = _all_configs()
    names = [s.strip() for s in args.systems.split(",") if s.strip()]
    unknown = [n for n in names if n not in configs]
    if unknown:
        print(f"unknown systems: {unknown}; choose from {sorted(configs)}", file=sys.stderr)
        return 2
    roles: Dict[str, str] = {}
    if args.roles:
        with open(args.roles, encoding="utf-8") as f:
            roles = (yaml.safe_load(f) or {}).get("roles") or {}
    allowed_docs = (
        {d for d, r in roles.items() if r in set(args.pool_roles.split(","))} if roles else None
    )
    if args.aspects:
        queries = crosswalk_cells(args.aspects)
        if args.only_aspects:
            wanted = set(args.only_aspects.split(","))
            queries = [q for q in queries if q["aspect"] in wanted]
    else:
        with open(args.queries, encoding="utf-8") as f:
            queries = (yaml.safe_load(f) or {}).get("queries") or []

    enc = Encoders(args.cache)
    # runs[system][query_id] = one ranked list per query phrasing
    runs: Dict[str, Dict[str, List[List[Dict[str, Any]]]]] = {}
    for name in names:
        print(f"[{name}] retrieving", file=sys.stderr)
        r = ExperimentRetriever(chunks, configs[name], enc, titles, allowed_docs=allowed_docs)
        runs[name] = {}
        for q in queries:
            jur = q.get("jurisdiction")
            jur = [jur] if isinstance(jur, str) else jur
            texts = q.get("queries") or [q["query"]]
            runs[name][q["query_id"]] = [r.retrieve(t, args.depth, jur or None) for t in texts]

    coarse = coarse_documents(chunks)
    sheet: List[Dict[str, Any]] = []
    for q in queries:
        by_prov: Dict[str, Dict[str, Any]] = {}
        hits: Dict[str, Dict[str, int]] = defaultdict(dict)
        for name in names:
            for ranked in runs[name][q["query_id"]]:
                for rank, c in enumerate(ranked, start=1):
                    for key in sorted(judgment_units(c, coarse)):
                        hits[key][name] = min(rank, hits[key].get(name, rank))
                        by_prov.setdefault(key, c)
        cands = []
        # Order by how many systems found the provision, then best rank, so the annotator
        # sees consensus candidates first; ordering does not affect the judgment itself.
        for key in sorted(by_prov, key=lambda k: (-len(hits[k]), min(hits[k].values()), k)):
            c = by_prov[key]
            meta = c.get("metadata") or {}
            cands.append(
                {
                    "provision": key,
                    "document_id": meta.get("document_id"),
                    "jurisdiction": meta.get("jurisdiction"),
                    "role": roles.get(str(meta.get("document_id")), "unknown"),
                    "section": meta.get("section") or "",
                    "chunk_id": c["id"],
                    "found_by": dict(sorted(hits[key].items())),
                    "text": " ".join(str(c.get("text") or "").split())[: args.excerpt],
                    "label": None,
                }
            )
        sheet.append({**{k: v for k, v in q.items() if k != "relevant"}, "candidates": cands})

    payload = {
        "systems": names,
        "depth": args.depth,
        "pool_roles": args.pool_roles if roles else "all",
        "chunk_level_documents": sorted(coarse),
        "labels": "2 operative / 1 related / 0 no",
        "queries": sheet,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        if args.out.endswith(".json"):
            json.dump(payload, f, ensure_ascii=False, indent=1)
        else:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True, width=100)
    total = sum(len(q["candidates"]) for q in sheet)
    print(f"wrote {total} candidates for {len(sheet)} queries to {args.out}", file=sys.stderr)
    return 0


def cmd_anchors(args: argparse.Namespace) -> int:
    chunks = read_manifest(args.store)
    by_id = {c["id"]: c for c in chunks}
    by_doc: Dict[str, List[str]] = defaultdict(list)
    for c in chunks:
        by_doc[str((c.get("metadata") or {}).get("document_id"))].append(c["id"])
    with open(args.pool, encoding="utf-8") as f:
        pool = yaml.safe_load(f) or {}

    # Only candidates within the depth actually annotated must carry a judgment; deeper
    # ones were never shown to the annotator and are treated as unjudged (not relevant).
    depth = int(pool.get("annotation_depth") or pool.get("depth") or 10**6)
    out_queries = []
    unjudged = 0
    for q in pool.get("queries") or []:
        relevant = []
        for cand in q.get("candidates") or []:
            if min((cand.get("found_by") or {"_": 0}).values()) > depth:
                continue
            label = cand.get("label")
            if label is None:
                unjudged += 1
                continue
            if int(label) < args.min_label:
                continue
            chunk = by_id.get(cand["chunk_id"])
            if chunk is None:
                print(
                    f"{q['query_id']}: chunk {cand['chunk_id']} no longer in store", file=sys.stderr
                )
                return 1
            others = [
                str(by_id[i].get("text") or "")
                for i in by_doc[cand["document_id"]]
                if i != chunk["id"]
            ]
            phrase = _anchor_phrase(str(chunk.get("text") or ""), others)
            anchor: Dict[str, Any] = {"document_id": cand["document_id"]}
            if phrase:
                anchor["contains"] = phrase
            else:
                anchor["chunk_id"] = chunk["id"]
            anchor["grade"] = int(label)
            relevant.append(anchor)
        entry = {k: v for k, v in q.items() if k not in ("candidates", "empty_cell")}
        if q.get("empty_cell") and relevant:
            print(f"{q['query_id']}: marked empty but has relevant candidates", file=sys.stderr)
            return 1
        # An empty crosswalk cell is a positive finding ("this jurisdiction's corpus has no
        # provision on this aspect"), kept explicitly so gap detection can be scored.
        entry["empty_cell"] = bool(q.get("empty_cell")) or not relevant
        entry["relevant"] = relevant
        out_queries.append(entry)
    if unjudged and not args.allow_unjudged:
        print(
            f"{unjudged} candidates still unlabelled; finish judging or pass --allow-unjudged",
            file=sys.stderr,
        )
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "version": args.version,
                "notes": (
                    f"Pooled over {', '.join(pool.get('systems') or [])} at depth "
                    f"{pool.get('depth')}; judged to depth {depth}."
                ),
                "queries": out_queries,
            },
            f,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--store", default=os.path.join(ROOT, "data", "regbot_store"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pool")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--queries", help="gold-style YAML of queries")
    src.add_argument("--aspects", help="aspect taxonomy; pools every aspect x jurisdiction cell")
    p.add_argument("--only-aspects", help="comma-separated aspect ids to pool (with --aspects)")
    p.add_argument("--roles", help="document_roles.yaml; restricts the pool by role")
    p.add_argument("--pool-roles", default="law,policy,guidance")
    p.add_argument("--systems", default="baseline,bm25_only,dense_only,fusion_sum,contextual")
    p.add_argument("--depth", type=int, default=10)
    p.add_argument("--excerpt", type=int, default=600)
    p.add_argument("--out", required=True)
    p.add_argument("--corpus-manifest", default=os.path.join(ROOT, "docs", "corpus_manifest.yaml"))
    p.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    a = sub.add_parser("anchors")
    a.add_argument("--pool", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--min-label", type=int, default=2)
    a.add_argument("--version", default="pooled-draft")
    a.add_argument("--allow-unjudged", action="store_true")
    args = ap.parse_args(argv)
    return cmd_pool(args) if args.cmd == "pool" else cmd_anchors(args)


if __name__ == "__main__":
    raise SystemExit(main())
