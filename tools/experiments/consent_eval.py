"""
Score consent → provision systems against a crosswalk gold standard.

Inputs
  --crosswalk  gold YAML produced by ``pool_candidates.py anchors`` from an annotated pool:
               one entry per (aspect, jurisdiction) cell with ``relevant`` anchors and
               ``empty_cell``
  --docs       consent-document set YAML written by ``consent_docs.py draft``: named
               ``scopes`` plus ``documents`` whose ``clauses`` carry frozen text and gold
               ``aspects`` (``[]`` for a clause that raises no governance aspect)

Gold provisions for a document under a scope are the union of crosswalk cells over the
document's aspects × the scope's jurisdictions. This construction is what makes the
benchmark cheap to extend: a new consent form needs only clause-level aspect labels, never
provision-level judgments.

Every (document, scope) pair is one evaluation instance; metrics are macro-averaged over
instances with bootstrap confidence intervals.

Metrics
  provision_recall@B   gold provisions covered by the top-B slots
  cell_coverage@B      non-empty gold cells with at least one provision in the top-B
  precision@B          share of returned slots that belong to a gold provision
  template_rate@B      share of returned slots taken by consent templates
  gap_precision / gap_recall
                       taxonomy aspects reported as unaddressed vs. the gold complement of
                       the document's aspects (systems that classify clauses only)
  clause_aspect_f1     micro F1 of predicted vs. gold clause aspects (oracle segmentation)

    python tools/experiments/consent_eval.py --crosswalk examples/eval/crosswalk/crosswalk_gold.yaml \\
        --docs examples/eval/consent_docs.yaml --segmentation oracle --out results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import yaml  # noqa: E402
from consent_docs import load_clause_texts  # noqa: E402
from src.regbot.evaluation import resolve_anchors  # noqa: E402
from src.regbot.significance import bootstrap_ci  # noqa: E402
from units import coarse_documents, judgment_units  # noqa: E402


def load_crosswalk(path: str, chunks: Sequence[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Resolve each cell's anchors to the set of gold judgment units; key = 'A08|EU'."""
    with open(path, encoding="utf-8") as f:
        gold = yaml.safe_load(f) or {}
    by_id = {c["id"]: c for c in chunks}
    coarse = coarse_documents(chunks)
    cells: Dict[str, Set[str]] = {}
    for q in gold.get("queries") or []:
        ids, unresolved = resolve_anchors(q.get("relevant"), chunks)
        if unresolved:
            raise ValueError(f"{q.get('query_id')}: {len(unresolved)} anchors do not resolve")
        provs: Set[str] = set()
        for i in ids:
            provs |= judgment_units(by_id[i], coarse)
        cells[f"{q['aspect']}|{q['jurisdiction'][0]}"] = provs
    return cells


def doc_aspects(doc: Dict[str, Any]) -> List[str]:
    """A document's gold aspects: the union over its labelled clauses."""
    found: Set[str] = set()
    for c in doc.get("clauses") or []:
        found |= set(c.get("aspects") or [])
    return sorted(found)


def gold_for(doc: Dict[str, Any], cells: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    aspects = doc.get("aspects") or doc_aspects(doc)
    return {
        f"{a}|{j}": cells.get(f"{a}|{j}", set()) for a in aspects for j in doc.get("scope") or []
    }


def score_document(
    ranked: Sequence[Dict[str, Any]],
    doc_gold: Dict[str, Set[str]],
    roles: Dict[str, str],
    budget: int,
    coarse: Optional[Set[str]] = None,
) -> Dict[str, float]:
    top = list(ranked[:budget])
    gold_all: Set[str] = set().union(*doc_gold.values()) if doc_gold else set()
    found: Set[str] = set()
    hits = 0
    templates = 0
    for c in top:
        keys = judgment_units(c, coarse or set())
        found |= keys
        if keys & gold_all:
            hits += 1
        doc = str((c.get("metadata") or {}).get("document_id"))
        if roles.get(doc) == "template":
            templates += 1
    nonempty = [k for k, v in doc_gold.items() if v]
    return {
        f"provision_recall@{budget}": len(found & gold_all) / len(gold_all) if gold_all else 0.0,
        f"cell_coverage@{budget}": (
            sum(1 for k in nonempty if doc_gold[k] & found) / len(nonempty) if nonempty else 0.0
        ),
        f"precision@{budget}": hits / len(top) if top else 0.0,
        f"template_rate@{budget}": templates / len(top) if top else 0.0,
    }


def score_gaps(
    reported: Sequence[str], addressed: Sequence[str], taxonomy: Sequence[str]
) -> Dict[str, float]:
    truth = set(taxonomy) - set(addressed)
    rep = set(reported)
    tp = len(rep & truth)
    return {
        "gap_precision": tp / len(rep) if rep else (1.0 if not truth else 0.0),
        "gap_recall": tp / len(truth) if truth else 1.0,
    }


def clause_aspect_scores(
    predicted: Sequence[Sequence[str]], gold: Sequence[Sequence[str]]
) -> Dict[str, float]:
    """Micro precision / recall / F1 over (clause, aspect) pairs."""
    tp = fp = fn = 0
    for p, g in zip(predicted, gold):
        ps, gs = set(p), set(g)
        tp += len(ps & gs)
        fp += len(ps - gs)
        fn += len(gs - ps)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"clause_aspect_precision": prec, "clause_aspect_recall": rec, "clause_aspect_f1": f1}


SYSTEMS = [
    ("whole", "none"),
    ("decompose", "none"),
    ("bridge", "aspect"),
    ("bridge", "hyde"),
    ("allocate", "aspect"),
    ("allocate", "hyde"),
    ("allocate", "both"),
]


def main(argv: Optional[Sequence[str]] = None) -> int:
    from consent_pipeline import ConsentPipeline

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--crosswalk", required=True)
    ap.add_argument("--docs", required=True)
    ap.add_argument("--budgets", default="8,24,48")
    ap.add_argument("--scopes", default="", help="comma-separated scope names; default all")
    ap.add_argument("--systems", default=",".join(f"{s}:{b}" for s, b in SYSTEMS))
    ap.add_argument("--segmentation", choices=["oracle", "auto"], default="oracle")
    ap.add_argument(
        "--aspects",
        default="zeroshot",
        help="zeroshot (pipeline classifier), oracle (gold clause labels), or a path to a "
        "predictions JSON from aspect_clf_llm.py; needs oracle segmentation unless zeroshot",
    )
    ap.add_argument("--retriever", default="baseline")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    pipe = ConsentPipeline(retriever_config=args.retriever, cache=args.cache)
    cells = load_crosswalk(args.crosswalk, pipe.any_doc.chunks)
    with open(args.docs, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    docs = [d for d in spec.get("documents") or [] if doc_aspects(d)]
    scopes: Dict[str, List[str]] = spec.get("scopes") or {}
    if args.scopes:
        scopes = {k: v for k, v in scopes.items() if k in set(args.scopes.split(","))}
    taxonomy = [a.id for a in pipe.aspects]
    coarse = coarse_documents(pipe.any_doc.chunks)
    budgets = [int(b) for b in args.budgets.split(",")]
    external: Optional[Dict[str, List[str]]] = None
    if args.aspects not in ("zeroshot", "oracle"):
        with open(args.aspects, encoding="utf-8") as f:
            external = json.load(f)["predictions"]
    if args.aspects != "zeroshot" and args.segmentation != "oracle":
        raise SystemExit("--aspects oracle / predictions requires --segmentation oracle")

    table: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    per_instance: List[Dict[str, Any]] = []
    for doc in docs:
        texts = load_clause_texts(doc)
        labelled = [c for c in doc["clauses"] if c.get("aspects") is not None]
        clause_texts = [texts[c["id"]] for c in labelled]
        clause_gold = [list(c["aspects"]) for c in labelled]
        with open(os.path.join(ROOT, doc["path"]), encoding="utf-8") as f:
            raw_text = f.read()
        text = "\n\n".join(clause_texts) if args.segmentation == "oracle" else raw_text
        clauses_arg = clause_texts if args.segmentation == "oracle" else None
        aspects_arg: Optional[List[List[str]]] = None
        if args.aspects == "oracle":
            aspects_arg = clause_gold
        elif external is not None:
            aspects_arg = [list(external.get(c["sha1"], [])) for c in labelled]
        excluded = set(doc.get("exclude_documents") or [])
        for scope_name, scope in scopes.items():
            doc_gold = gold_for({**doc, "scope": scope}, cells)
            for spec_name in args.systems.split(","):
                system, bridge = spec_name.split(":")
                res = pipe.run(
                    text,
                    system=system,
                    scope=scope,
                    budget=max(budgets) * 2,
                    bridge=bridge,
                    clauses=clauses_arg,
                    clause_aspects=aspects_arg,
                )
                ranked = [
                    c
                    for c in res.ranked
                    if str((c.get("metadata") or {}).get("document_id")) not in excluded
                ]
                row: Dict[str, float] = {}
                for b in budgets:
                    row.update(score_document(ranked, doc_gold, pipe.roles, b, coarse))
                if res.clause_aspects:
                    row.update(score_gaps(res.gap_aspects, doc_aspects(doc), taxonomy))
                    if clauses_arg is not None:
                        row.update(
                            clause_aspect_scores([a for _, a in res.clause_aspects], clause_gold)
                        )
                for m, v in row.items():
                    table[spec_name][m].append(v)
                per_instance.append(
                    {"doc_id": doc["doc_id"], "scope": scope_name, "system": spec_name, **row}
                )
                print(
                    f"{doc['doc_id'][:34]:<34} {scope_name:<9} {spec_name:<16} "
                    f"R@{budgets[-1]}={row.get(f'provision_recall@{budgets[-1]}', 0):.3f} "
                    f"cov={row.get(f'cell_coverage@{budgets[-1]}', 0):.3f}",
                    file=sys.stderr,
                )

    summary = {
        spec_name: {
            m: {
                "mean": round(sum(v) / len(v), 4),
                "ci95": [round(x, 4) for x in bootstrap_ci(v, resamples=2000)],
                "n": len(v),
            }
            for m, v in ms.items()
        }
        for spec_name, ms in table.items()
    }
    metrics = sorted({m for ms in summary.values() for m in ms})
    print("| system | " + " | ".join(metrics) + " |")
    print("|---|" + "---|" * len(metrics))
    for spec_name, ms in summary.items():
        print(
            f"| {spec_name} | "
            + " | ".join(f"{ms[m]['mean']:.3f}" if m in ms else "—" for m in metrics)
            + " |"
        )
    # Per-scope view at the largest budget: the Asian scope is where the cross-jurisdictional
    # allocation matters most, and a pooled average would hide it.
    primary = f"provision_recall@{budgets[-1]}"
    cover = f"cell_coverage@{budgets[-1]}"
    print(f"\nPer scope ({primary} / {cover}):")
    print("| system | " + " | ".join(scopes) + " |")
    print("|---|" + "---|" * len(scopes))
    for spec_name in table:
        cells = []
        for scope_name in scopes:
            rows = [
                r for r in per_instance if r["system"] == spec_name and r["scope"] == scope_name
            ]
            if rows:
                cells.append(
                    f"{sum(r[primary] for r in rows) / len(rows):.3f} / "
                    f"{sum(r[cover] for r in rows) / len(rows):.3f}"
                )
            else:
                cells.append("—")
        print(f"| {spec_name} | " + " | ".join(cells) + " |")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "documents": [d["doc_id"] for d in docs],
                    "scopes": scopes,
                    "segmentation": args.segmentation,
                    "aspects": args.aspects,
                    "retriever": args.retriever,
                    "summary": summary,
                    "instances": per_instance,
                },
                f,
                indent=1,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
