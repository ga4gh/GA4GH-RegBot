"""
Clause → aspect classification against the consent benchmark's gold clause labels.

The Decompose step needs to know which governance aspects a clause raises. This script
scores zero-shot variants of that classifier — embedding model, how aspect prototypes are
built, and the decision rule — with micro precision / recall / F1 over (clause, aspect)
pairs. Clauses labelled ``[]`` (no governance aspect) count: any aspect predicted for them
is a false positive, so a threshold that allows "none" can win.

    python tools/experiments/aspect_clf_eval.py --docs examples/eval/consent_docs.yaml
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402
import yaml  # noqa: E402
from ablate import Encoders  # noqa: E402
from consent_docs import load_clause_texts  # noqa: E402
from consent_eval import clause_aspect_scores  # noqa: E402
from consent_pipeline import Aspect, load_aspects  # noqa: E402

PROTOTYPES = {
    "def+cues": lambda a: [f"{a.label}. {a.definition}", *a.cues],
    "cues": lambda a: list(a.cues),
    "def": lambda a: [f"{a.label}. {a.definition}"],
    "def+cues+norm": lambda a: [f"{a.label}. {a.definition}", *a.cues, *a.normative_queries],
}


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) or 1.0)


def predict(
    sims: np.ndarray,
    ids: List[str],
    *,
    margin: float,
    threshold: float,
    max_aspects: int,
    rule: str,
) -> List[str]:
    order = np.argsort(-sims)
    best = float(sims[order[0]])
    if best < threshold:
        return []
    if rule == "margin":
        return [ids[i] for i in order[:max_aspects] if sims[i] >= best - margin]
    # "relative": keep aspects whose similarity is within a fraction of the top score
    return [ids[i] for i in order[:max_aspects] if sims[i] >= best * (1 - margin)]


def supervised_rows(
    clauses: List[Tuple[str, List[str]]],
    gold: List[List[str]],
    ids: List[str],
    enc: Encoders,
    models: List[str],
) -> List[Dict[str, Any]]:
    """
    Leave-one-document-out one-vs-rest logistic regression on clause embeddings.

    A supervised reference point for the zero-shot classifier: with ~230 labelled clauses
    it shows how much of the gap is the prototype design rather than the embedding space.
    Documents are held out whole so a form never trains on its own clauses.
    """
    from sklearn.linear_model import LogisticRegression

    docs = [d for d, _ in clauses]  # doc id per clause, parallel to ``gold``
    out: List[Dict[str, Any]] = []
    for model in models:
        X = np.stack([_unit(enc.encode_query(model, t)) for t, _ in clause_texts_only(clauses)])
        for c_reg in (1.0, 4.0, 16.0):
            preds: List[List[str]] = [[] for _ in clauses]
            for held in sorted(set(docs)):
                train = [i for i, d in enumerate(docs) if d != held]
                test = [i for i, d in enumerate(docs) if d == held]
                for aspect in ids:
                    y = np.array([1 if aspect in gold[i] else 0 for i in train])
                    if y.sum() == 0:
                        continue
                    clf = LogisticRegression(C=c_reg, class_weight="balanced", max_iter=2000)
                    clf.fit(X[train], y)
                    for i, p in zip(test, clf.predict_proba(X[test])[:, 1]):
                        if p >= 0.5:
                            preds[i].append(aspect)
            scores = clause_aspect_scores(preds, gold)
            out.append(
                {
                    "model": model.split("/")[-1],
                    "prototype": "supervised-LODO",
                    "rule": "logreg",
                    "margin": c_reg,
                    "threshold": 0.5,
                    "max": "-",
                    **{k.replace("clause_aspect_", ""): round(v, 4) for k, v in scores.items()},
                }
            )
    return out


def clause_texts_only(clauses: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[str]]]:
    return [(t, g) for _, (t, g) in enumerate(_TEXTS)]


_TEXTS: List[Tuple[str, List[str]]] = []


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", default=os.path.join(ROOT, "examples", "eval", "consent_docs.yaml"))
    ap.add_argument(
        "--models",
        default="BAAI/bge-small-en-v1.5,sentence-transformers/all-MiniLM-L6-v2,BAAI/bge-base-en-v1.5",
    )
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--languages", default="en", help="comma-separated document languages to score")
    ap.add_argument(
        "--supervised", action="store_true", help="add leave-one-document-out logistic regression"
    )
    args = ap.parse_args(argv)

    with open(args.docs, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    clauses: List[Tuple[str, List[str]]] = []  # (doc_id, aspects) per clause
    languages = set(args.languages.split(","))
    for doc in spec.get("documents") or []:
        if doc.get("language") not in languages:
            continue
        texts = load_clause_texts(doc)
        for c in doc.get("clauses") or []:
            if c.get("aspects") is not None:
                _TEXTS.append((texts[c["id"]], list(c["aspects"])))
                clauses.append((doc["doc_id"], list(c["aspects"])))
    gold = [g for _, g in _TEXTS]
    aspects: List[Aspect] = load_aspects()
    ids = [a.id for a in aspects]
    print(
        f"{len(clauses)} labelled clauses, {sum(1 for g in gold if not g)} with no aspect",
        file=sys.stderr,
    )

    enc = Encoders(args.cache)
    rows: List[Dict[str, Any]] = []
    for model in args.models.split(","):
        clause_vecs = np.stack([_unit(enc.encode_query(model, t)) for t, _ in _TEXTS])
        for proto_name, build in PROTOTYPES.items():
            protos = np.stack(
                [
                    _unit(np.mean([enc.encode_query(model, t) for t in build(a)], axis=0))
                    for a in aspects
                ]
            )
            sims_all = clause_vecs @ protos.T
            for rule, margin, threshold, max_aspects in itertools.product(
                ("margin", "relative"), (0.0, 0.02, 0.04, 0.06), (0.0, 0.5, 0.55, 0.6), (1, 2, 3)
            ):
                preds = [
                    predict(
                        sims_all[i],
                        ids,
                        margin=margin,
                        threshold=threshold,
                        max_aspects=max_aspects,
                        rule=rule,
                    )
                    for i in range(len(_TEXTS))
                ]
                scores = clause_aspect_scores(preds, gold)
                rows.append(
                    {
                        "model": model.split("/")[-1],
                        "prototype": proto_name,
                        "rule": rule,
                        "margin": margin,
                        "threshold": threshold,
                        "max": max_aspects,
                        **{k.replace("clause_aspect_", ""): round(v, 4) for k, v in scores.items()},
                    }
                )
    if args.supervised:
        rows.extend(supervised_rows(clauses, gold, ids, enc, args.models.split(",")))
    rows.sort(key=lambda r: -r["f1"])
    cols = ["model", "prototype", "rule", "margin", "threshold", "max", "precision", "recall", "f1"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows[: args.top]:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    # The production default, for reference.
    for r in rows:
        if (
            r["model"] == "bge-small-en-v1.5"
            and r["prototype"] == "def+cues"
            and r["rule"] == "margin"
            and r["margin"] == 0.04
            and r["threshold"] == 0.0
            and r["max"] == 2
        ):
            print(
                "\nproduction-like default (bge-small, def+cues, margin 0.04, no threshold, max 2):",
                r,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
