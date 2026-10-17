"""
Seed a crosswalk pool with the human-labelled provisions of the 41-query gold set.

Aspect-query pooling reaches about two thirds of the provisions that question-specific
queries find, so the anchors of ``examples/eval/gold_ga4gh.yaml`` — mapped to aspects by
``gold_query_aspects.yaml`` — are added to the matching (aspect, jurisdiction) cells as
candidates at depth 0. They carry ``seed`` (the source query) and no label: the annotator
judges them like any other candidate, and the LLM pre-labellers can be re-run on them.

    python tools/experiments/seed_pool.py --pool crosswalk_pool_v0.2.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Dict, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import yaml  # noqa: E402
from src.regbot.evaluation import resolve_anchors  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402
from units import coarse_documents, judgment_units  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pool", required=True, help="pool JSON, updated in place (a .bak copy is kept)"
    )
    ap.add_argument("--store", default=os.path.join(ROOT, "data", "regbot_store"))
    ap.add_argument("--gold", default=os.path.join(ROOT, "examples", "eval", "gold_ga4gh.yaml"))
    ap.add_argument(
        "--mapping",
        default=os.path.join(ROOT, "examples", "eval", "crosswalk", "gold_query_aspects.yaml"),
    )
    ap.add_argument(
        "--roles",
        default=os.path.join(ROOT, "examples", "eval", "crosswalk", "document_roles.yaml"),
    )
    ap.add_argument("--excerpt", type=int, default=1000)
    args = ap.parse_args(argv)

    chunks = read_manifest(args.store)
    by_id = {c["id"]: c for c in chunks}
    coarse = coarse_documents(chunks)
    with open(args.roles, encoding="utf-8") as f:
        roles: Dict[str, str] = yaml.safe_load(f)["roles"]
    with open(args.mapping, encoding="utf-8") as f:
        mapping: Dict[str, str] = yaml.safe_load(f)["aspects"]
    with open(args.gold, encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    with open(args.pool, encoding="utf-8") as f:
        pool = json.load(f)
    cells = {q["query_id"]: q for q in pool["queries"]}

    added = skipped_template = present = no_cell = 0
    for q in gold["queries"]:
        aspect = mapping.get(q["query_id"])
        if not aspect:
            continue
        ids, _ = resolve_anchors(q.get("relevant"), chunks)
        for cid in sorted(ids):
            chunk = by_id[cid]
            meta = chunk.get("metadata") or {}
            doc = str(meta.get("document_id"))
            if roles.get(doc) == "template":
                skipped_template += 1
                continue
            cell = cells.get(f"{aspect}-{meta.get('jurisdiction')}")
            if cell is None:
                no_cell += 1
                continue
            for unit in sorted(judgment_units(chunk, coarse)):
                if any(c["provision"] == unit for c in cell["candidates"]):
                    present += 1
                    continue
                cell["candidates"].append(
                    {
                        "provision": unit,
                        "document_id": doc,
                        "jurisdiction": meta.get("jurisdiction"),
                        "role": roles.get(doc, "unknown"),
                        "section": meta.get("section") or "",
                        "chunk_id": cid,
                        "found_by": {"gold_v0.9": 0},
                        "seed": q["query_id"],
                        "text": " ".join(str(chunk.get("text") or "").split())[: args.excerpt],
                        "label": None,
                    }
                )
                added += 1
    shutil.copy(args.pool, args.pool + ".bak")
    pool.setdefault("seeds", []).append({"source": os.path.basename(args.gold), "added": added})
    with open(args.pool, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=1)
    print(
        f"added {added} seeded candidates; {present} already pooled; {skipped_template} in templates; {no_cell} without a cell"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
