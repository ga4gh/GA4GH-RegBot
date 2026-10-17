"""
Pilot: does sending a multi-aspect document as ONE query lose provisions?

Production (`RegBot.compliance_report_and_chunks`) retrieves with the entire consent text as
a single query. A consent form raises many governance aspects at once — withdrawal,
cross-border transfer, secondary use, re-identification — and a single ranked list of k
slots has to cover all of them.

This pilot measures that with existing gold labels only. A pseudo-document is the
concatenation of ``m`` gold questions; its gold provisions are the union of theirs. Systems
receive the same slot budget and are scored on provision recall over the union and on
*aspect coverage* (fraction of the m questions with at least one gold provision returned).

  single      the concatenated text as one query (production behaviour)
  rr          each segment retrieved separately; lists interleaved round-robin
  rrf         each segment retrieved separately; lists fused by reciprocal rank

Segmentation here is oracle (one segment per question), so ``rr`` is an upper bound on
what automatic segmentation of a real consent form could reach with the same retriever.

    python tools/experiments/multi_aspect_pilot.py --samples 150
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Set

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from ablate import Config, Encoders, ExperimentRetriever  # noqa: E402
from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402
from src.regbot.evaluation import load_gold_set, resolve_anchors  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402
from src.regbot.significance import bootstrap_ci  # noqa: E402
from src.regbot.types import provision_keys  # noqa: E402


def provisions_of(chunks: Sequence[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for c in chunks:
        out |= provision_keys(c)
    return out


def interleave(
    lists: Sequence[Sequence[Dict[str, Any]]], budget: int, cap: int = 2
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    used: Dict[str, int] = defaultdict(int)
    depth = max((len(x) for x in lists), default=0)
    for r in range(depth):
        for lst in lists:
            if r >= len(lst) or len(out) >= budget:
                continue
            c = lst[r]
            keys = provision_keys(c)
            if c["id"] in seen or any(used[k] >= cap for k in keys):
                continue
            seen.add(c["id"])
            for k in keys:
                used[k] += 1
            out.append(c)
    return out[:budget]


def rrf_merge(
    lists: Sequence[Sequence[Dict[str, Any]]], budget: int, cap: int = 2
) -> List[Dict[str, Any]]:
    score: Dict[str, float] = defaultdict(float)
    rec: Dict[str, Dict[str, Any]] = {}
    for lst in lists:
        for rank, c in enumerate(lst):
            score[c["id"]] += 1.0 / (60 + rank + 1)
            rec[c["id"]] = c
    out: List[Dict[str, Any]] = []
    used: Dict[str, int] = defaultdict(int)
    for cid in sorted(score, key=lambda i: (-score[i], i)):
        keys = provision_keys(rec[cid])
        if any(used[k] >= cap for k in keys):
            continue
        for k in keys:
            used[k] += 1
        out.append(rec[cid])
        if len(out) >= budget:
            break
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=os.path.join(ROOT, "data", "regbot_store"))
    ap.add_argument("--gold", default=os.path.join(ROOT, "examples", "eval", "gold_ga4gh.yaml"))
    ap.add_argument("--samples", type=int, default=150)
    ap.add_argument("--ms", default="1,2,3,4,6")
    ap.add_argument("--budgets", default="8,16,24")
    ap.add_argument("--embedder", default=None, help="override the dense model")
    ap.add_argument("--out")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    args = ap.parse_args(argv)

    chunks = read_manifest(args.store)
    by_id = {c["id"]: c for c in chunks}
    gold = load_gold_set(args.gold)
    titles = {
        d["document_id"]: d.get("title", "")
        for d in load_corpus_manifest(os.path.join(ROOT, "docs", "corpus_manifest.yaml")).get(
            "documents", []
        )
    }
    cfg = Config(name="baseline")
    if args.embedder:
        cfg = Config(name="pilot", embedder=args.embedder)
    retr = ExperimentRetriever(chunks, cfg, Encoders(args.cache), titles)

    items = []
    for q in gold["queries"]:
        ids, _ = resolve_anchors(q.get("relevant"), chunks)
        items.append(
            {
                "id": q["query_id"],
                "text": q["query"].strip(),
                "gold": provisions_of([by_id[i] for i in ids]),
            }
        )

    # Per-segment ranked lists are cached; segments are reused across samples.
    max_budget = max(int(b) for b in args.budgets.split(","))
    seg_cache: Dict[str, List[Dict[str, Any]]] = {}

    def seg_list(text: str) -> List[Dict[str, Any]]:
        if text not in seg_cache:
            seg_cache[text] = retr.retrieve(text, max_budget, None)
        return seg_cache[text]

    rng = random.Random(7)
    results: Dict[str, Any] = {}
    for m in [int(x) for x in args.ms.split(",")]:
        combos = [rng.sample(items, m) for _ in range(args.samples if m > 1 else len(items))]
        if m == 1:
            combos = [[it] for it in items]
        for budget in [int(b) for b in args.budgets.split(",")]:
            rows: Dict[str, Dict[str, List[float]]] = {
                s: {"recall": [], "coverage": []} for s in ("single", "rr", "rrf")
            }
            for combo in combos:
                union = set().union(*(it["gold"] for it in combo))
                doc = "\n\n".join(it["text"] for it in combo)
                outs = {
                    "single": retr.retrieve(doc, budget, None),
                    "rr": interleave([seg_list(it["text"]) for it in combo], budget),
                    "rrf": rrf_merge([seg_list(it["text"]) for it in combo], budget),
                }
                for sname, out in outs.items():
                    found = provisions_of(out)
                    rows[sname]["recall"].append(len(found & union) / len(union))
                    rows[sname]["coverage"].append(sum(1 for it in combo if found & it["gold"]) / m)
            key = f"m={m},budget={budget}"
            results[key] = {}
            for sname, r in rows.items():
                rec = sum(r["recall"]) / len(r["recall"])
                cov = sum(r["coverage"]) / len(r["coverage"])
                results[key][sname] = {
                    "provision_recall": round(rec, 4),
                    "provision_recall_ci95": [
                        round(x, 4) for x in bootstrap_ci(r["recall"], resamples=2000)
                    ],
                    "aspect_coverage": round(cov, 4),
                }
            line = " | ".join(
                f"{s}: R={v['provision_recall']:.3f} cov={v['aspect_coverage']:.3f}"
                for s, v in results[key].items()
            )
            print(f"{key:<18} {line}", flush=True)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"samples": args.samples, "results": results}, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
