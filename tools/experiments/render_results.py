"""
Turn one or more ``consent_eval.py`` result files into the paper's results tables.

    python tools/experiments/render_results.py --budget 24 results/silver_llama3/eval_*.json

Each input file is one evaluation run (a crosswalk standard × an aspect source × a
segmentation). The main table has a row per (run, system) with the primary metrics at the
chosen budget and bootstrap intervals; the second table breaks provision recall and cell
coverage down by scope.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence


def _cell(stats: Optional[Dict[str, Any]], ci: bool) -> str:
    if not stats:
        return "—"
    if ci:
        lo, hi = stats["ci95"]
        return f"{stats['mean']:.3f} [{lo:.2f}, {hi:.2f}]"
    return f"{stats['mean']:.3f}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--budget", type=int, default=24)
    ap.add_argument("--ci", action="store_true", help="show 95% bootstrap intervals")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    runs = []
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        aspects = data.get("aspects", "zeroshot")
        tag = os.path.basename(aspects).replace("clause_aspects_", "").replace(".json", "")
        runs.append((os.path.basename(path), tag, data))

    b = args.budget
    metrics = [
        (f"provision_recall@{b}", f"recall@{b}"),
        (f"cell_coverage@{b}", f"coverage@{b}"),
        (f"precision@{b}", f"precision@{b}"),
        (f"template_rate@{b}", f"templates@{b}"),
        ("gap_precision", "gap P"),
        ("gap_recall", "gap R"),
        ("clause_aspect_f1", "clause F1"),
    ]
    lines: List[str] = []
    lines.append("| aspects | system | " + " | ".join(m[1] for m in metrics) + " |")
    lines.append("|---|---|" + "---|" * len(metrics))
    for _, tag, data in runs:
        for system, stats in data["summary"].items():
            lines.append(
                f"| {tag} | {system} | "
                + " | ".join(_cell(stats.get(m[0]), args.ci) for m in metrics)
                + " |"
            )
    docs = len(runs[0][2].get("documents") or [])
    scopes = list((runs[0][2].get("scopes") or {}).keys())
    lines.insert(
        0,
        f"{docs} documents × {len(scopes)} scopes ({', '.join(scopes)}); budget {b}; segmentation {runs[0][2].get('segmentation')}.",
    )
    lines.insert(1, "")

    lines += ["", f"Per scope: provision recall@{b} / cell coverage@{b}", ""]
    lines.append("| aspects | system | " + " | ".join(scopes) + " |")
    lines.append("|---|---|" + "---|" * len(scopes))
    for _, tag, data in runs:
        by: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for inst in data.get("instances") or []:
            by[inst["system"]][inst["scope"]].append(inst)
        for system in data["summary"]:
            cells = []
            for scope in scopes:
                rows = by[system].get(scope) or []
                if rows:
                    r = sum(x[f"provision_recall@{b}"] for x in rows) / len(rows)
                    c = sum(x[f"cell_coverage@{b}"] for x in rows) / len(rows)
                    cells.append(f"{r:.3f} / {c:.3f}")
                else:
                    cells.append("—")
            lines.append(f"| {tag} | {system} | " + " | ".join(cells) + " |")

    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
