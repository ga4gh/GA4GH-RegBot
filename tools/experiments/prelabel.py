"""
LLM pre-labelling of a crosswalk candidate pool.

Each pooled passage is judged against the cell's aspect definition and jurisdiction with the
same three-way scale the human annotator uses (ANNOTATION_GUIDE.md). Labels are written
back into the pool file under ``llm_labels[<model>]`` and, for the model named
``--primary``, mirrored to ``llm_label`` / ``llm_reason`` so the annotation tool can show
them once blind mode is switched off.

The purpose is twofold: to turn human labelling from judging-from-scratch into verifying,
and to measure LLM-vs-human agreement, which is itself a result. Pre-labels never enter
the gold standard on their own.

Runs against a local Ollama server at temperature 0 with a fixed seed; every judgment is
cached on disk by (model, prompt) so re-runs are free and reproducible.

    python tools/experiments/prelabel.py --pool crosswalk_pool_v0.1.json --model qwen3:14b --depth 5
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


from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402

SYSTEM_PROMPT = """You assist a regulatory reviewer (data protection officer, research ethics board, or data access committee). Decide whether a passage from a legal or policy document is a provision such a reviewer in the given jurisdiction would need to consult when a research consent form addresses the given governance aspect.

Labels:
2 = operative: the passage itself states a rule, right, duty, prohibition, condition, or procedure on this aspect that applies in this jurisdiction. A fragment of an operative provision counts as operative. Guidance and soft law count as operative when they state what must or should be done.
1 = related: on topic but not operative - a definition the rule depends on, a recital or preamble, an exception cross-referenced from elsewhere, or a rule on a neighbouring aspect.
0 = not relevant: a different topic, or shares vocabulary only.

Judge the passage shown, not the document it comes from. Answer with JSON only, in the form {"label": 0, "reason": "one sentence"}."""


def build_prompt(cell: Dict[str, Any], cand: Dict[str, Any], titles: Dict[str, str]) -> str:
    doc = str(cand.get("document_id"))
    return (
        f"ASPECT: {cell.get('aspect_label')}\n"
        f"ASPECT DEFINITION: {cell.get('definition')}\n"
        f"JURISDICTION: {', '.join(cell.get('jurisdiction') or [])}\n"
        f"DOCUMENT: {titles.get(doc, doc)} [{cand.get('role')}]\n"
        f"SECTION: {cand.get('section') or '(none)'}\n"
        f"PASSAGE:\n{cand.get('text')}"
    )


class OllamaJudge:
    def __init__(self, model: str, cache_dir: str) -> None:
        self.model = model
        self.cache_dir = os.path.join(cache_dir, model.replace("/", "__").replace(":", "_"))
        os.makedirs(self.cache_dir, exist_ok=True)
        self.base = os.getenv("REGBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        import httpx

        self.client = httpx.Client(trust_env=False, timeout=600)

    def judge(self, prompt: str) -> Dict[str, Any]:
        key = hashlib.sha256(f"{self.model}\x00{SYSTEM_PROMPT}\x00{prompt}".encode()).hexdigest()[
            :32
        ]
        path = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 7, "num_predict": 160, "num_ctx": 4096},
        }
        if self.model.startswith(("qwen3", "deepseek-r1", "gpt-oss")):
            body["think"] = False
        t0 = time.time()
        r = self.client.post(f"{self.base}/api/chat", json=body)
        r.raise_for_status()
        raw = str(r.json().get("message", {}).get("content") or "")
        label, reason = _parse(raw)
        out = {
            "label": label,
            "reason": reason,
            "raw": raw[:400],
            "seconds": round(time.time() - t0, 2),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        return out


def _parse(raw: str) -> tuple[Optional[int], str]:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < 0:
            return None, "unparseable"
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None, "unparseable"
    try:
        label = int(obj.get("label"))
    except (TypeError, ValueError, AttributeError):
        return None, "no label"
    if label not in (0, 1, 2):
        return None, f"label out of range: {label}"
    return label, " ".join(str(obj.get("reason") or "").split())[:300]


def _best_rank(cand: Dict[str, Any]) -> int:
    return min((cand.get("found_by") or {"_": 10**6}).values())


def _save(path: str, pool: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pool", required=True, help="pool JSON; updated in place")
    ap.add_argument("--model", default="qwen3:14b")
    ap.add_argument("--depth", type=int, default=5, help="judge candidates with best rank <= depth")
    ap.add_argument(
        "--primary", default=None, help="model whose labels fill llm_label (default: --model)"
    )
    ap.add_argument("--limit", type=int, default=0, help="stop after N new judgments (0 = all)")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/prelabel"))
    ap.add_argument("--corpus-manifest", default=os.path.join(ROOT, "docs", "corpus_manifest.yaml"))
    ap.add_argument("--save-every", type=int, default=25)
    args = ap.parse_args(argv)
    primary = args.primary or args.model

    with open(args.pool, encoding="utf-8") as f:
        pool = json.load(f)
    titles = {
        d["document_id"]: d.get("title", "")
        for d in load_corpus_manifest(args.corpus_manifest).get("documents", [])
    }
    judge = OllamaJudge(args.model, args.cache)

    # Shallow ranks first, so the depth the human annotates is pre-labelled before deeper ones.
    todo: List[tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    for cell in pool.get("queries") or []:
        for cand in cell.get("candidates") or []:
            rank = _best_rank(cand)
            if rank <= args.depth and args.model not in (cand.get("llm_labels") or {}):
                todo.append((rank, cell, cand))
    todo.sort(key=lambda t: (t[0], t[1]["query_id"]))
    print(
        f"[{args.model}] {len(todo)} candidates to judge at depth <= {args.depth}", file=sys.stderr
    )

    done = 0
    t0 = time.time()
    seconds: List[float] = []
    for rank, cell, cand in todo:
        out = judge.judge(build_prompt(cell, cand, titles))
        cand.setdefault("llm_labels", {})[args.model] = {
            "label": out["label"],
            "reason": out["reason"],
        }
        if args.model == primary:
            cand["llm_label"] = out["label"]
            cand["llm_reason"] = out["reason"]
        done += 1
        seconds.append(float(out.get("seconds") or 0.0))
        if done % args.save_every == 0 or done == len(todo):
            _save(args.pool, pool)
            rate = (time.time() - t0) / done
            eta = rate * (len(todo) - done) / 60
            print(
                f"[{args.model}] {done}/{len(todo)} judged, {rate:.1f}s each, ~{eta:.0f} min left",
                file=sys.stderr,
            )
        if args.limit and done >= args.limit:
            _save(args.pool, pool)
            break

    labels = [
        c.get("llm_labels", {}).get(args.model, {}).get("label")
        for q in pool["queries"]
        for c in q["candidates"]
    ]
    counts = {str(k): labels.count(k) for k in (2, 1, 0, None)}
    print(f"[{args.model}] label counts {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
