"""
Render a crosswalk gold (or silver) file as a readable aspect × jurisdiction matrix.

Each cell lists the provisions judged operative — document and section — so a reviewer
can read the crosswalk the way REWS's regional jurisdiction notes are read, and so empty
cells (no provision in the corpus for that aspect and jurisdiction) are visible at a glance.

    python tools/experiments/render_crosswalk.py --crosswalk results/silver_llama3.yaml --out crosswalk.md
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402
from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402
from src.regbot.evaluation import resolve_anchors  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402


def _short_title(title: str, limit: int = 48) -> str:
    title = title.split(" — ", 1)[-1] if " — " in title else title
    return title if len(title) <= limit else title[: limit - 1] + "…"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--crosswalk", required=True)
    ap.add_argument("--store", default=os.path.join(ROOT, "data", "regbot_store"))
    ap.add_argument(
        "--aspects", default=os.path.join(ROOT, "examples", "eval", "crosswalk", "aspects.yaml")
    )
    ap.add_argument("--corpus-manifest", default=os.path.join(ROOT, "docs", "corpus_manifest.yaml"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    chunks = read_manifest(args.store)
    by_id = {c["id"]: c for c in chunks}
    titles = {
        d["document_id"]: d.get("title", d["document_id"])
        for d in load_corpus_manifest(args.corpus_manifest).get("documents", [])
    }
    with open(args.aspects, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    labels = {a["id"]: a["label"] for a in spec["aspects"]}
    jurisdictions: List[str] = list(spec["jurisdictions"])
    with open(args.crosswalk, encoding="utf-8") as f:
        gold = yaml.safe_load(f)

    cells: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
    counts: Dict[str, int] = defaultdict(int)
    for q in gold.get("queries") or []:
        ids, _ = resolve_anchors(q.get("relevant"), chunks)
        entries: Dict[str, Any] = {}
        for i in sorted(ids):
            meta = by_id[i].get("metadata") or {}
            doc = str(meta.get("document_id"))
            section = str(meta.get("section") or "").strip()
            key = f"{doc}|{section}"
            if key not in entries:
                label = _short_title(titles.get(doc, doc))
                entries[key] = (
                    f"{label} § {section[:40]}"
                    if section
                    else f"{label} (p{meta.get('page')})"
                    if meta.get("page")
                    else label
                )
        cells[q["aspect"]][q["jurisdiction"][0]] = list(entries.values())
        counts[q["jurisdiction"][0]] += len(entries)

    lines = [
        f"# Crosswalk — {os.path.basename(args.crosswalk)}",
        "",
        f"Version `{gold.get('version')}`"
        + (f", silver from `{gold['silver_from']}`" if gold.get("silver_from") else "")
        + ".",
        "Each cell lists provisions judged operative for that aspect in that jurisdiction; "
        "`—` marks a cell judged to have no provision in the corpus.",
        "",
        "| aspect | " + " | ".join(jurisdictions) + " |",
        "|---|" + "---|" * len(jurisdictions),
    ]
    for aid, label in labels.items():
        row = []
        for j in jurisdictions:
            provs = cells.get(aid, {}).get(j)
            if provs is None:
                row.append("·")
            elif not provs:
                row.append("—")
            else:
                shown = "<br>".join(provs[:4]) + (
                    f"<br>+{len(provs) - 4} more" if len(provs) > 4 else ""
                )
                row.append(shown)
        lines.append(f"| **{aid}** {label} | " + " | ".join(row) + " |")
    lines += [
        "",
        "Provisions per jurisdiction: " + ", ".join(f"{j} {counts[j]}" for j in jurisdictions),
    ]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
