"""
Build and review the consent-document side of the consent → provision benchmark.

``draft`` turns every fetched consent document (data/consent_benchmark/manifest.json) into
a benchmark entry: the text is trimmed to the consent form proper, segmented into clauses,
and each clause receives zero-shot aspect proposals. Clause boundaries are frozen by a hash
of each clause's text in the YAML; the texts themselves live in a gitignored companion file
(``data/consent_benchmark/clauses/<doc_id>.json``) because not every source may be
redistributed, and are regenerated from the fetched documents by re-running ``draft``. A
hash mismatch is reported rather than silently accepted. Existing ``aspects`` labels are
preserved for clauses whose text is unchanged.

``review`` prints a compact listing (id, proposals, opening words) for labelling, and
``stats`` summarises label coverage.

    python tools/experiments/consent_docs.py draft --out examples/eval/consent_docs.yaml
    python tools/experiments/consent_docs.py review --docs examples/eval/consent_docs.yaml --doc us-gtex-live-donor-consent
    python tools/experiments/consent_docs.py stats --docs examples/eval/consent_docs.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import yaml  # noqa: E402

MANIFEST = os.path.join(ROOT, "data", "consent_benchmark", "manifest.json")
CLAUSE_DIR = os.path.join(ROOT, "data", "consent_benchmark", "clauses")

SCOPES: Dict[str, List[str]] = {
    "framework": ["GA4GH", "INTL"],
    "eu": ["EU", "GA4GH"],
    "asia": ["SG", "HK", "TW", "KR", "JP", "CN"],
    "all": ["GA4GH", "INTL", "EU", "SG", "HK", "TW", "KR", "JP", "CN"],
}

# How each source is trimmed to the consent text proper. Markers are verbatim substrings.
PREPARE: Dict[str, Dict[str, Any]] = {
    "us-nih-osp-secondary-research-sample": {
        "start_marker": "IV. Sample Language Components",
        "drop_patterns": [r"^Instructions:", r"^In\s*$", r"^structions:"],
    },
    "us-nhgri-gds-sample-language": {
        "start_marker": "Sample Language Aligned to Informational Elements",
        "end_marker": "Last updated:",
        "line_paragraphs": True,
        "split_before": [r"Example \d+:"],
    },
    "us-nih-irb-consent-library": {
        "start_marker": "GENOMIC SEQUENCING",
        "start_occurrence": 2,
        # The table of contents is cut away by the start marker, so the body heading is
        # the first remaining occurrence.
        "end_marker": "HIV TESTING",
    },
    "us-all-of-us-consent-to-join": {"start_marker": "Consent to Join the"},
    "us-1000-genomes-consent": {"start_marker": "CONSENT TO PARTICIPATE"},
    "us-emerge-consent": {
        "start_marker": "BIOBANK PURPOSE",
        "drop_patterns": [r"^(Passive Sentences|Reading Ease|Grade Level)\b"],
    },
    "us-gtex-live-donor-consent": {"start_marker": "Addendum Seeking Your Permission"},
    "us-beskow-simplified-biobank-consent": {
        "start_marker": "Exhibit S1",
        "drop_patterns": [r"MERGEFORMAT"],
    },
    "eu-uppsala-biobank-registry-consent-template": {},
    "ee-estonian-biobank-gene-donor-consent": {"start_marker": "GENE DONOR CONSENT FORM"},
    "kr-bioethics-form-34-research-consent": {
        # A statutory form flattened from a table: the numbered explanations run inline.
        "split_before": [
            r"(?<=\s)[1-6]\.\s(?=[가-힣])",
            r"※ 위의 모든",
            r"동의 내용",
            r"보존 기간 내 2차적",
            r"2차적 사용을 위한 제공 시",
            r"\(뒤쪽\)",
        ],
        "strip_patterns": [r"210mm×297mm\[[^\]]*\)\]?"],
    },
    "jp-amed-model-explanation-text": {
        # The guidance preamble is skipped; "3．AMED 文案" opens the model text proper.
        "start_marker": "3．AMED 文案",
        "start_occurrence": 2,  # the first occurrence is the table of contents
        "drop_patterns": [r"^\s*\d{1,2}\s*$"],
    },
    "tw-mohw-biobank-consent-template": {},
}


def _load_docs(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"version": "0.1", "scopes": SCOPES, "documents": []}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def clause_hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def _preview(text: str, chars: int = 80) -> str:
    return " ".join(text.split())[:chars]


def load_clause_texts(doc: Dict[str, Any]) -> Dict[str, str]:
    """Full clause texts for a benchmark document, verified against the YAML hashes."""
    path = os.path.join(CLAUSE_DIR, f"{doc['doc_id']}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} is missing; run `python tools/experiments/consent_docs.py draft` after "
            "fetching the consent documents"
        )
    with open(path, encoding="utf-8") as f:
        texts: Dict[str, str] = json.load(f)["clauses"]
    for c in doc.get("clauses") or []:
        text = texts.get(c["id"])
        if text is None or clause_hash(text) != c.get("sha1"):
            raise ValueError(
                f"{doc['doc_id']} {c['id']}: clause text does not match the benchmark hash; "
                "the fetched document or the segmenter changed — re-run draft and re-check labels"
            )
    return texts


def cmd_draft(args: argparse.Namespace) -> int:
    from consent_pipeline import AspectClassifier, Encoders, load_aspects, prepare_text, segment

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = [d for d in json.load(f)["documents"] if d.get("status") == "ok"]
    languages = set(args.languages.split(","))
    existing = _load_docs(args.out)
    old_by_doc = {d["doc_id"]: d for d in existing.get("documents") or []}
    clf = AspectClassifier(load_aspects(), Encoders(args.cache), args.classifier)

    documents: List[Dict[str, Any]] = []
    for rec in manifest:
        if rec.get("language") not in languages:
            continue
        with open(os.path.join(ROOT, rec["text_path"]), encoding="utf-8") as f:
            raw = f.read()
        prep = PREPARE.get(rec["doc_id"], {})
        clauses = segment(prepare_text(raw, **prep))
        old_entries = old_by_doc.get(rec["doc_id"], {}).get("clauses") or []
        old_labels = {
            (c.get("sha1") or clause_hash(c.get("text") or "")): c.get("aspects")
            for c in old_entries
        }
        # Fallback when a clause's interior changed (a stripped header, a merged line) but
        # its opening did not: re-attach the label by the first 60 characters of the preview.
        old_by_preview = {
            _preview(c.get("preview") or c.get("text") or "", 60): c.get("aspects")
            for c in old_entries
        }
        entries = []
        texts: Dict[str, str] = {}
        kept = 0
        for i, clause in enumerate(clauses, start=1):
            cid = f"c{i:02d}"
            digest = clause_hash(clause)
            proposals = [f"{a}:{s:.2f}" for a, s in clf.scores(clause)[:3]]
            aspects = old_labels.get(digest)
            if aspects is None:
                # Every old clause whose opening occurs inside this clause contributes its
                # label: a clause that absorbed its page-broken continuation keeps both.
                flat = " ".join(clause.split())
                parts = [
                    a for pv, a in old_by_preview.items() if pv and pv in flat and a is not None
                ]
                if parts:
                    aspects = sorted({x for a in parts for x in a})
            kept += 1 if aspects is not None else 0
            entries.append(
                {
                    "id": cid,
                    "sha1": digest,
                    "aspects": aspects,
                    "proposed": proposals,
                    "preview": _preview(clause),
                }
            )
            texts[cid] = clause
        os.makedirs(CLAUSE_DIR, exist_ok=True)
        with open(os.path.join(CLAUSE_DIR, f"{rec['doc_id']}.json"), "w", encoding="utf-8") as f:
            json.dump({"doc_id": rec["doc_id"], "clauses": texts}, f, ensure_ascii=False, indent=1)
        documents.append(
            {
                "doc_id": rec["doc_id"],
                "title": rec["title"],
                "path": rec["text_path"],
                "language": rec["language"],
                "origin": rec["origin"],
                "text_type": rec["text_type"],
                "licence": rec["licence"],
                "prepare": prep,
                "clauses": entries,
            }
        )
        print(
            f"{rec['doc_id']:<48} {len(clauses):>3} clauses ({kept} labels kept)", file=sys.stderr
        )

    out = {
        "version": existing.get("version", "0.1"),
        "status": existing.get(
            "status",
            "DRAFT — clause aspects proposed by a zero-shot classifier and labelled by the "
            "contributor; not yet independently verified.",
        ),
        "scopes": existing.get("scopes") or SCOPES,
        "documents": documents,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=100)
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    docs = _load_docs(args.docs)
    for d in docs.get("documents") or []:
        if args.doc and d["doc_id"] != args.doc:
            continue
        texts = load_clause_texts(d)
        print(f"=== {d['doc_id']} — {d['title']}")
        for c in d.get("clauses") or []:
            label = ",".join(c["aspects"]) if c.get("aspects") is not None else "?"
            body = " ".join(texts[c["id"]].split())[: args.chars]
            print(
                f"[{c['id']}] gold={label:<9} prop={' '.join(c.get('proposed') or [])}\n      {body}"
            )
        print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    docs = _load_docs(args.docs)
    total = labelled = 0
    aspect_counts: Dict[str, int] = {}
    for d in docs.get("documents") or []:
        for c in d.get("clauses") or []:
            total += 1
            if c.get("aspects") is not None:
                labelled += 1
                for a in c["aspects"]:
                    aspect_counts[a] = aspect_counts.get(a, 0) + 1
    print(
        f"{labelled}/{total} clauses labelled across {len(docs.get('documents') or [])} documents"
    )
    for a, n in sorted(aspect_counts.items()):
        print(f"  {a}: {n}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--out", default=os.path.join(ROOT, "examples", "eval", "consent_docs.yaml"))
    d.add_argument("--languages", default="en")
    d.add_argument("--classifier", default="BAAI/bge-base-en-v1.5")
    d.add_argument("--cache", default=os.path.expanduser("~/.cache/regbot/embeddings"))
    r = sub.add_parser("review")
    r.add_argument("--docs", default=os.path.join(ROOT, "examples", "eval", "consent_docs.yaml"))
    r.add_argument("--doc")
    r.add_argument("--chars", type=int, default=320)
    st = sub.add_parser("stats")
    st.add_argument("--docs", default=os.path.join(ROOT, "examples", "eval", "consent_docs.yaml"))
    args = ap.parse_args(argv)
    return {"draft": cmd_draft, "review": cmd_review, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
