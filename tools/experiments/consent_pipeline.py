"""
Consent form → applicable provisions: baselines and the Decompose → Bridge → Allocate method.

Every system returns a ranked list of chunks under the same slot budget so they can be
scored identically. Systems:

  whole        the entire consent form as one query (production behaviour today)
  decompose    one query per clause; lists interleaved round-robin
  bridge       per clause, the query is rewritten into the register of statute text:
                 --bridge aspect  normative queries of the clause's detected aspects
                 --bridge hyde    an LLM-written hypothetical governing provision
                 --bridge both    aspect queries plus the hypothetical provision
  allocate     bridge + jurisdiction-stratified retrieval per (aspect, jurisdiction) cell,
               slots allocated round-robin over cells, templates excluded from provision
               slots; also reports taxonomy aspects the form never addresses (gap candidates)

Clause → aspect classification is zero-shot: cosine similarity between the clause and each
aspect's prototype (definition + participant-facing cues), keeping aspects within a margin
of the best match.

    python tools/experiments/consent_pipeline.py demo --consent examples/data/sample_consent_complex.txt \
        --scope EU,SG,GA4GH --system allocate --bridge aspect --budget 24
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402
import yaml  # noqa: E402
from ablate import SUITES, Encoders, ExperimentRetriever  # noqa: E402
from src.regbot.corpus_manifest import load_corpus_manifest  # noqa: E402
from src.regbot.ingestion import read_manifest  # noqa: E402
from src.regbot.types import provision_keys  # noqa: E402

CROSSWALK_DIR = os.path.join(ROOT, "examples", "eval", "crosswalk")
NORMATIVE_ROLES = {"law", "policy", "guidance"}

# --------------------------------------------------------------------------- segmentation

_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\d{1,2}[.)]\s+|[A-Z]\.\s+|[IVX]{1,4}\.\s+)")
_INLINE_CAPS = re.compile(r"^(?:[A-Z][A-Z'’/&-]{2,}\s+)+[A-Z][A-Z'’/&-]{2,}[?:]?")
_BULLET = re.compile(r"^\s*(?:[-•*●○▪]|\(?[a-z0-9]{1,2}\)|\d{1,2}\))\s+")
_TERMINAL = (".", "?", "!", ":", ";", ")")


def _norm_line(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.split())).lower()


def _nth_index(text: str, needle: str, n: int) -> int:
    """Offset of the n-th occurrence of ``needle`` (a table of contents may hold the first)."""
    pos = -1
    for _ in range(max(1, n)):
        pos = text.find(needle, pos + 1)
        if pos < 0:
            return -1
    return pos


def prepare_text(
    text: str,
    *,
    start_marker: Optional[str] = None,
    end_marker: Optional[str] = None,
    drop_patterns: Sequence[str] = (),
    min_repeats: int = 3,
    line_paragraphs: bool = False,
    split_before: Sequence[str] = (),
    start_occurrence: int = 1,
    end_occurrence: int = 1,
) -> str:
    """
    Trim a document to the consent text proper and drop page furniture.

    ``start_marker`` / ``end_marker`` cut away wrappers — an archive's "Sample Consent
    Document 9" preamble, or the other sections of a consent library. Short lines whose
    digit-normalised form repeats at least ``min_repeats`` times (running headers, "Page 3
    of 12") are removed, as are lines matching any ``drop_patterns`` regex. Page breaks are
    joined so a paragraph that crosses a page stays one paragraph. ``line_paragraphs``
    treats every line as a paragraph (HTML extraction), and ``split_before`` inserts a
    paragraph break before each regex match.
    """
    if start_marker:
        i = _nth_index(text, start_marker, start_occurrence)
        if i >= 0:
            text = text[i:]
    if end_marker:
        j = _nth_index(text, end_marker, end_occurrence)
        if j >= 0:
            text = text[:j]
    for pattern in split_before:
        # Web pages often run several sample clauses into one paragraph ("Example 1: …
        # Example 2: …"); a split pattern inserts a paragraph break before each match.
        text = re.sub(f"(?<!\\n\\n)(?={pattern})", "\n\n", text)
    if line_paragraphs:
        # HTML extraction emits one paragraph per line with no blank lines between them.
        text = "\n\n".join(ln for ln in text.splitlines())
    lines = text.splitlines()
    counts = Counter(_norm_line(ln) for ln in lines if ln.strip() and len(ln) < 120)
    drops = [re.compile(p) for p in drop_patterns]
    kept: List[str] = []
    for ln in lines:
        s = ln.strip()
        if s == "\f":
            continue
        if s and len(ln) < 120 and counts[_norm_line(ln)] >= min_repeats:
            continue
        if s and any(d.search(ln) for d in drops):
            continue
        kept.append(ln.rstrip())
    return "\n".join(kept)


def _is_heading(line: str, prev: str) -> bool:
    """
    Does ``line`` open a new clause?

    Consent forms extracted from PDF rarely keep blank lines between paragraphs, so clause
    boundaries are recovered from the shapes headings take in these documents: numbered
    ("3. Sharing"), question-style ("What will you ask me to do?"), ALL-CAPS (also when the
    first sentence runs on inline, "WHAT IS INVOLVED? If you agree…"), and short title-case
    lines without terminal punctuation. The last two only count when the previous line
    ended a sentence, which keeps hard-wrapped lines inside their paragraph.
    """
    s = line.strip()
    if not s or len(s) > 100:
        return False
    if _HEADING.match(s):
        return True
    words = s.split()
    letters = [c for c in s if c.isalpha()]
    caps_ratio = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
    if len(letters) >= 3 and caps_ratio >= 0.8:
        return True
    if _INLINE_CAPS.match(s):
        return True
    prev_s = prev.strip()
    prev_done = not prev_s or prev_s.endswith(_TERMINAL)
    if not prev_done:
        return False
    if s.endswith("?") and len(words) <= 12:
        return True
    if s.endswith(":") and len(words) <= 6:
        return True
    return (
        1 <= len(words) <= 8
        and len(s) <= 60
        and s[0].isupper()
        and not s.endswith(_TERMINAL)
        and not s.endswith(",")
        and not _BULLET.match(s)
    )


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(\"“])")


def _split_long(block: str, max_chars: int) -> List[str]:
    """Split an over-long block at sentence boundaries into pieces of about ``max_chars``."""
    if len(block) <= max_chars:
        return [block]
    flat = " ".join(block.split())
    pieces: List[str] = []
    cur = ""
    for sentence in _SENTENCE_END.split(flat):
        if cur and len(cur) + 1 + len(sentence) > max_chars:
            pieces.append(cur)
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def segment(
    text: str, *, min_chars: int = 120, max_chars: int = 1200, max_segments: int = 80
) -> List[str]:
    """
    Split a consent form into clauses.

    A heading (see :func:`_is_heading`) or a blank line after enough text starts a new
    clause; blocks longer than ``max_chars`` are split at sentence boundaries. Fragments shorter than ``min_chars`` merge into the following clause unless they
    are a headed clause with a body of their own ("10. Contact / Questions may be…"), so a
    heading travels with its body instead of becoming a near-empty query.
    """
    blocks: List[List[str]] = []
    cur: List[str] = []
    prev = ""
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            if cur and len("\n".join(cur)) >= min_chars:
                blocks.append(cur)
                cur = []
            prev = ""
            continue
        if cur and _is_heading(ln, prev):
            blocks.append(cur)
            cur = []
        cur.append(s)
        prev = ln
    if cur:
        blocks.append(cur)

    merged: List[str] = []
    carry = ""
    for lines in blocks:
        headed = _is_heading(lines[0], "") and len(lines) >= 2
        b = "\n".join(lines)
        b = (carry + "\n" + b).strip() if carry else b
        if len(b) < min_chars and not headed:
            carry = b
            continue
        merged.append(b)
        carry = ""
    if carry:
        if merged:
            merged[-1] = merged[-1] + "\n" + carry
        else:
            merged.append(carry)
    # A form with neither headings nor blank lines would otherwise be one clause; long
    # blocks are split at sentence boundaries so every clause stays a readable unit.
    out: List[str] = []
    for b in merged:
        out.extend(_split_long(b, max_chars))
    return out[:max_segments]


# --------------------------------------------------------------------------- aspects


@dataclass
class Aspect:
    id: str
    label: str
    definition: str
    cues: List[str]
    normative_queries: List[str]


def load_aspects(path: str = os.path.join(CROSSWALK_DIR, "aspects.yaml")) -> List[Aspect]:
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    return [
        Aspect(
            id=a["id"],
            label=a["label"],
            definition=" ".join(str(a.get("definition") or "").split()),
            cues=list(a.get("consent_cues") or []),
            normative_queries=list(a.get("normative_queries") or []),
        )
        for a in spec.get("aspects") or []
    ]


def load_roles(path: str = os.path.join(CROSSWALK_DIR, "document_roles.yaml")) -> Dict[str, str]:
    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("roles") or {}


class AspectClassifier:
    """Zero-shot clause → aspects by embedding similarity to aspect prototypes."""

    def __init__(self, aspects: List[Aspect], enc: Encoders, model: str, margin: float = 0.05):
        self.aspects = aspects
        self.enc = enc
        self.model = model
        self.margin = margin
        protos = []
        for a in aspects:
            vecs = [enc.encode_query(model, t) for t in [f"{a.label}. {a.definition}", *a.cues]]
            v = np.mean(vecs, axis=0)
            protos.append(v / (np.linalg.norm(v) or 1.0))
        self.protos = np.stack(protos)

    def scores(self, clause: str) -> List[Tuple[str, float]]:
        v = self.enc.encode_query(self.model, clause)
        sims = self.protos @ v
        return sorted(((a.id, float(s)) for a, s in zip(self.aspects, sims)), key=lambda x: -x[1])

    def classify(self, clause: str, max_aspects: int = 2) -> List[str]:
        ranked = self.scores(clause)
        best = ranked[0][1]
        return [a for a, s in ranked[:max_aspects] if s >= best - self.margin]


# --------------------------------------------------------------------------- HyDE bridge


class HypotheticalProvisionWriter:
    """
    Rewrites a participant-facing clause as the provision that would govern it.

    Uses a local Ollama model at temperature 0; outputs are cached on disk keyed by model,
    prompt and clause so experiment runs are reproducible and never re-query the LLM.
    """

    PROMPT = (
        "You are drafting legal text. Below is a clause from a research participant consent "
        "form. Write the provision of a data-protection or research-ethics law or policy "
        "that would govern what this clause describes. Use formal statutory language "
        '("shall", "the data subject", "the controller", "the researcher"). Write 2-4 '
        "sentences. Do not cite article numbers. Output only the provision.\n\nCLAUSE:\n"
    )

    def __init__(self, model: str = "llama3", cache_dir: Optional[str] = None) -> None:
        self.model = model
        self.cache_dir = cache_dir or os.path.expanduser("~/.cache/regbot/hyde")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.base = os.getenv("REGBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    def __call__(self, clause: str) -> str:
        key = hashlib.sha256(f"{self.model}\x00{self.PROMPT}\x00{clause}".encode()).hexdigest()[:24]
        path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return str(json.load(f)["text"])
        import httpx

        r = httpx.Client(trust_env=False, timeout=180).post(
            f"{self.base}/api/generate",
            json={
                "model": self.model,
                "prompt": self.PROMPT + clause.strip(),
                "stream": False,
                "options": {"temperature": 0, "seed": 7, "num_predict": 220},
            },
        )
        r.raise_for_status()
        text = " ".join(str(r.json().get("response") or "").split())
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"model": self.model, "clause": clause, "text": text}, f, ensure_ascii=False)
        return text


# --------------------------------------------------------------------------- systems


@dataclass
class Result:
    ranked: List[Dict[str, Any]]
    cells: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    exemplars: List[Dict[str, Any]] = field(default_factory=list)
    clause_aspects: List[Tuple[str, List[str]]] = field(default_factory=list)
    gap_aspects: List[str] = field(default_factory=list)


def _interleave(
    lists: Sequence[Sequence[Dict[str, Any]]], budget: int, cap: int = 2
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    used: Dict[str, int] = defaultdict(int)
    for r in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if len(out) >= budget:
                return out
            if r >= len(lst):
                continue
            c = lst[r]
            keys = provision_keys(c)
            if c["id"] in seen or any(used[k] >= cap for k in keys):
                continue
            seen.add(c["id"])
            for k in keys:
                used[k] += 1
            out.append(c)
    return out


class ConsentPipeline:
    def __init__(
        self,
        *,
        retriever_config: str = "baseline",
        classifier_model: str = "BAAI/bge-small-en-v1.5",
        cache: str = os.path.expanduser("~/.cache/regbot/embeddings"),
        store: str = os.path.join(ROOT, "data", "regbot_store"),
        hyde_model: str = "llama3",
    ) -> None:
        configs = {c.name: c for suite in SUITES.values() for c in suite}
        chunks = read_manifest(store)
        titles = {
            d["document_id"]: d.get("title", "")
            for d in load_corpus_manifest(os.path.join(ROOT, "docs", "corpus_manifest.yaml")).get(
                "documents", []
            )
        }
        self.enc = Encoders(cache)
        self.roles = load_roles()
        normative = {d for d, r in self.roles.items() if r in NORMATIVE_ROLES}
        templates = {d for d, r in self.roles.items() if r == "template"}
        cfg = configs[retriever_config]
        self.any_doc = ExperimentRetriever(chunks, cfg, self.enc, titles)
        self.normative = ExperimentRetriever(chunks, cfg, self.enc, titles, allowed_docs=normative)
        self.templates = ExperimentRetriever(chunks, cfg, self.enc, titles, allowed_docs=templates)
        self.aspects = load_aspects()
        self.by_aspect = {a.id: a for a in self.aspects}
        self.classifier = AspectClassifier(self.aspects, self.enc, classifier_model)
        self.hyde = HypotheticalProvisionWriter(hyde_model)

    def _bridge_queries(self, clause: str, aspects: List[str], bridge: str) -> List[str]:
        qs: List[str] = []
        if bridge in ("aspect", "both"):
            for a in aspects:
                qs.extend(self.by_aspect[a].normative_queries)
        if bridge in ("hyde", "both"):
            qs.append(self.hyde(clause))
        if bridge == "none":
            qs.append(clause)
        return qs

    def run(
        self,
        consent: str,
        *,
        system: str,
        scope: Optional[List[str]],
        budget: int,
        bridge: str = "aspect",
        per_query: int = 8,
        clauses: Optional[List[str]] = None,
        clause_aspects: Optional[List[List[str]]] = None,
    ) -> Result:
        """
        ``clauses`` bypasses the segmenter (oracle segmentation from the benchmark) and
        ``clause_aspects`` bypasses the classifier (oracle or externally predicted aspects,
        parallel to ``clauses``), so retrieval error can be measured on its own.
        """
        if system == "whole":
            return Result(self.any_doc.retrieve(consent, budget, scope))

        clauses = list(clauses) if clauses is not None else segment(consent)
        if system == "decompose":
            lists = [self.any_doc.retrieve(c, per_query, scope) for c in clauses]
            return Result(_interleave(lists, budget))

        if clause_aspects is not None:
            labelled = [(c, list(a)) for c, a in zip(clauses, clause_aspects)]
        else:
            labelled = [(c, self.classifier.classify(c)) for c in clauses]
        detected = sorted({a for _, aspects in labelled for a in aspects})
        gaps = [a.id for a in self.aspects if a.id not in detected]
        exemplars = _interleave([self.templates.retrieve(c, 2, None) for c in clauses], 6)

        if system == "bridge":
            lists = []
            for clause, aspects in labelled:
                for q in self._bridge_queries(clause, aspects, bridge):
                    lists.append(self.normative.retrieve(q, per_query, scope))
            return Result(
                _interleave(lists, budget),
                exemplars=exemplars,
                clause_aspects=[(c[:60], a) for c, a in labelled],
                gap_aspects=gaps,
            )

        if system == "allocate":
            jurisdictions = scope or sorted({j for j in self._all_jurisdictions()})
            clauses_for: Dict[str, List[str]] = defaultdict(list)
            for clause, aspects in labelled:
                for a in aspects:
                    clauses_for[a].append(clause)
            cells: Dict[str, List[Dict[str, Any]]] = {}
            for a in detected:
                queries: List[str] = []
                for clause in clauses_for[a]:
                    queries.extend(self._bridge_queries(clause, [a], bridge))
                queries = list(dict.fromkeys(queries))
                for j in jurisdictions:
                    lists = [self.normative.retrieve(q, per_query, [j]) for q in queries]
                    cells[f"{a}|{j}"] = _interleave(lists, per_query)
            ranked = _interleave(list(cells.values()), budget)
            return Result(
                ranked,
                cells=cells,
                exemplars=exemplars,
                clause_aspects=[(c[:60], a) for c, a in labelled],
                gap_aspects=gaps,
            )

        raise ValueError(f"unknown system {system}")

    def _all_jurisdictions(self) -> Set[str]:
        return {str((c.get("metadata") or {}).get("jurisdiction")) for c in self.any_doc.chunks}


# --------------------------------------------------------------------------- CLI


def _fmt(c: Dict[str, Any], roles: Dict[str, str]) -> str:
    m = c.get("metadata") or {}
    doc = str(m.get("document_id"))
    sec = str(m.get("section") or "")[:60]
    return f"{m.get('jurisdiction', '?'):<5} {roles.get(doc, '?'):<8} {doc} | {sec}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sgm = sub.add_parser("segments", help="print clauses with proposed aspects, for labelling")
    sgm.add_argument("--consent", required=True)
    sgm.add_argument("--chars", type=int, default=400)
    sgm.add_argument("--classifier", default="BAAI/bge-small-en-v1.5")
    sgm.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    d = sub.add_parser("demo")
    d.add_argument("--consent", required=True)
    d.add_argument("--scope", default="", help="comma-separated jurisdictions; empty = all")
    d.add_argument(
        "--system", default="allocate", choices=["whole", "decompose", "bridge", "allocate"]
    )
    d.add_argument("--bridge", default="aspect", choices=["none", "aspect", "hyde", "both"])
    d.add_argument("--budget", type=int, default=24)
    d.add_argument("--retriever", default="baseline")
    d.add_argument("--classifier", default="BAAI/bge-small-en-v1.5")
    d.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    args = ap.parse_args(argv)

    if args.cmd == "segments":
        clf = AspectClassifier(load_aspects(), Encoders(args.cache), args.classifier)
        with open(args.consent, encoding="utf-8") as f:
            clauses = segment(f.read())
        for i, clause in enumerate(clauses):
            props = ", ".join(f"{a}:{s:.2f}" for a, s in clf.scores(clause)[:3])
            body = " ".join(clause.split())[: args.chars]
            print(f"[{i:02d}] {props}\n     {body}\n")
        return 0

    pipe = ConsentPipeline(
        retriever_config=args.retriever, classifier_model=args.classifier, cache=args.cache
    )
    with open(args.consent, encoding="utf-8") as f:
        text = f.read()
    scope = [s.strip() for s in args.scope.split(",") if s.strip()] or None
    res = pipe.run(text, system=args.system, scope=scope, budget=args.budget, bridge=args.bridge)
    if res.clause_aspects:
        print("## clause → aspects")
        for clause, aspects in res.clause_aspects:
            print(f"  {', '.join(aspects):<9} {clause!r}")
        print("## aspects never addressed (gap candidates):", ", ".join(res.gap_aspects) or "none")
    print(f"## ranked provisions (budget {args.budget})")
    for i, c in enumerate(res.ranked, 1):
        print(f"{i:>3}. {_fmt(c, pipe.roles)}")
    if res.exemplars:
        print("## template exemplars (separate channel)")
        for c in res.exemplars:
            print("     " + _fmt(c, pipe.roles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
