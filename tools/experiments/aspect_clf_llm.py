"""
LLM clause → aspect classification (zero-shot, local Ollama), scored against gold labels.

The whole taxonomy (id, label, definition) is in the prompt; the model returns the aspect
ids a clause raises, possibly none. Outputs are cached by (model, prompt) and written as
``{clause_sha1: [aspects]}`` so ``consent_eval.py --aspects llm`` can reuse them without
re-querying.

    python tools/experiments/aspect_clf_llm.py --model qwen3:14b --out data/consent_benchmark/clause_aspects_qwen3.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import yaml  # noqa: E402
from consent_docs import load_clause_texts  # noqa: E402
from consent_eval import clause_aspect_scores  # noqa: E402
from consent_pipeline import load_aspects  # noqa: E402

SYSTEM = """You classify clauses of research consent forms by the data-governance aspects they address. A reviewer will use your labels to look up the laws and policies that apply to each clause.

Rules:
- Assign every aspect the clause substantively addresses (it may be several, usually one or two).
- Assign none when the clause raises no governance aspect (physical risks of a blood draw, costs, a signature block, a title, instructions to the form's author).
- Judge what the clause says, not the document it comes from.
Answer with JSON only: {"aspects": ["A08", "A11"]} or {"aspects": []}."""


def build_prompt(taxonomy: str, clause: str) -> str:
    return f"ASPECTS:\n{taxonomy}\n\nCLAUSE:\n{clause.strip()}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", default=os.path.join(ROOT, "examples", "eval", "consent_docs.yaml"))
    ap.add_argument("--model", default="qwen3:14b")
    ap.add_argument("--out", required=True)
    ap.add_argument("--languages", default="en", help="comma-separated document languages to score")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/clause_aspects"))
    args = ap.parse_args(argv)

    import httpx

    base = os.getenv("REGBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    client = httpx.Client(trust_env=False, timeout=600)
    cache_dir = os.path.join(args.cache, args.model.replace(":", "_").replace("/", "__"))
    os.makedirs(cache_dir, exist_ok=True)

    aspects = load_aspects()
    valid = {a.id for a in aspects}
    taxonomy = "\n".join(f"{a.id} {a.label}: {a.definition}" for a in aspects)

    with open(args.docs, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    items: List[Dict[str, Any]] = []
    languages = set(args.languages.split(","))
    for doc in spec.get("documents") or []:
        if doc.get("language") not in languages:
            continue
        texts = load_clause_texts(doc)
        for c in doc.get("clauses") or []:
            if c.get("aspects") is not None:
                items.append(
                    {
                        "doc": doc["doc_id"],
                        "id": c["id"],
                        "sha1": c["sha1"],
                        "text": texts[c["id"]],
                        "gold": list(c["aspects"]),
                    }
                )

    predictions: Dict[str, List[str]] = {}
    t0 = time.time()
    for n, it in enumerate(items, start=1):
        prompt = build_prompt(taxonomy, it["text"])
        key = hashlib.sha256(f"{args.model}\x00{SYSTEM}\x00{prompt}".encode()).hexdigest()[:32]
        path = os.path.join(cache_dir, key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)["raw"]
        else:
            body: Dict[str, Any] = {
                "model": args.model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "seed": 7, "num_predict": 80, "num_ctx": 4096},
            }
            if args.model.startswith(("qwen3", "deepseek-r1", "gpt-oss")):
                body["think"] = False
            r = client.post(f"{base}/api/chat", json=body)
            r.raise_for_status()
            raw = str(r.json().get("message", {}).get("content") or "")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"raw": raw}, f)
        try:
            parsed = json.loads(raw)
            pred = [a for a in (parsed.get("aspects") or []) if a in valid]
        except (json.JSONDecodeError, AttributeError):
            pred = []
        predictions[it["sha1"]] = sorted(set(pred))
        if n % 25 == 0 or n == len(items):
            print(
                f"[{args.model}] {n}/{len(items)} ({(time.time() - t0) / n:.1f}s each)",
                file=sys.stderr,
            )

    scores = clause_aspect_scores(
        [predictions[i["sha1"]] for i in items], [i["gold"] for i in items]
    )
    none_gold = [i for i in items if not i["gold"]]
    none_acc = (
        sum(1 for i in none_gold if not predictions[i["sha1"]]) / len(none_gold)
        if none_gold
        else 0.0
    )
    print(
        f"{args.model}: "
        + ", ".join(f"{k.replace('clause_aspect_', '')}={v:.3f}" for k, v in scores.items())
        + f", none-accuracy={none_acc:.3f}"
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "scores": scores, "predictions": predictions}, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
