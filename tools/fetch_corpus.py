#!/usr/bin/env python3
"""
Rebuild the primary-source corpus under ``data/corpus/`` from its official publishers.

Without this, the corpus is a set of opaque files nobody can regenerate or audit. Run it
from the repository root:

    python tools/fetch_corpus.py --list          # show targets, fetch nothing
    python tools/fetch_corpus.py --only gdpr     # refresh one target
    python tools/fetch_corpus.py                 # refresh everything
    python tools/fetch_corpus.py --check         # validate files already on disk

**Every fetch is validated before it is written.** An earlier run silently captured
Singapore and Japan *tables of contents* instead of the statutes — the Singapore file
contained zero occurrences of "shall not". A table of contents is worse than nothing in a
retrieval corpus: it matches query vocabulary and contains no rules. `must_contain` and
`min_words` make that failure loud, and a target that fails validation is not written.

Sources whose publishers serve a JavaScript shell (Hong Kong e-Legislation, Korea KLRI)
cannot be fetched here and remain contributor summaries; see docs/eval_results.md §4c.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from lxml import html as LH

ROOT = Path(__file__).resolve().parents[1]
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
POLITE_DELAY_S = 1.5

BOILERPLATE = re.compile(
    r"^(skip to|search|menu|share this|sign up|subscribe|cookie|newsletter|"
    r"follow us|back to top|related (news|posts)|previous|next|latest news|"
    r"our products|read more|view all|all news|home)\b",
    re.I,
)

#: Navigation strings that survive BOILERPLATE because they read like content. Matched
#: against the whole normalised line, so a provision merely mentioning REWS is unaffected.
NAV_EXACT = frozenset(
    {
        "latest news",
        "regulatory & ethics work stream (rews)",
        "regulatory and ethics work stream (rews)",
        "our products",
        "product documentation",
        "news",
        "blog",
        "events",
        "publications",
    }
)


@dataclass
class Target:
    key: str
    title: str
    url: str
    out: str
    extractor: str = "html"
    #: Phrases that must appear, case-insensitively, or the fetch is rejected. These are
    #: operative wording — their absence means we captured navigation, not law.
    must_contain: List[str] = field(default_factory=list)
    min_words: int = 150
    note: str = ""


TARGETS: List[Target] = [
    Target(
        key="gdpr",
        title="Regulation (EU) 2016/679 (GDPR), consolidated English text",
        url="https://publications.europa.eu/resource/celex/32016R0679",
        out="data/corpus/P1/gdpr-full-text-2016-679.txt",
        extractor="cellar",
        must_contain=["Article 35", "Article 9", "shall not"],
        min_words=40000,
        note="EU Publications Office CELLAR, content-negotiated to English XHTML.",
    ),
    # Two separate Acts, each numbering its articles from 1. Kept as separate documents so
    # a provision key like "Article 8" is unambiguous — merged, both Acts contributed an
    # Article 8 and the section label could not say which law it came from.
    Target(
        key="tw-biobank",
        title="Taiwan — Human Biobank Management Act (official English)",
        url="https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=L0020164",
        out="data/corpus/P2/TW/human-biobank-management-act.txt",
        extractor="moj_tw",
        must_contain=["Article 8", "withdraw"],
        min_words=3000,
        note="Ministry of Justice official English translation.",
    ),
    Target(
        key="tw-pdpa",
        title="Taiwan — Personal Data Protection Act (official English)",
        url="https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=I0050021",
        out="data/corpus/P2/TW/personal-data-protection-act.txt",
        extractor="moj_tw",
        must_contain=["Article 21", "personal data"],
        min_words=6000,
        note="Ministry of Justice official English translation.",
    ),
    Target(
        key="ga4gh-psp",
        title="GA4GH Privacy and Security Policy v1.0",
        url="https://drive.google.com/uc?export=download&id=1zJV3ZZMpyKEdbEH7OR_-iqWzRkSpIMSO",
        out="data/corpus/P0/ga4gh-privacy-security-policy.pdf",
        extractor="binary",
        min_words=0,
        note="PDF linked from ga4gh.org/document/privacy-and-security-policy/.",
    ),
]

# GA4GH pages that publish their text as HTML. Same extractor, so kept as a table.
GA4GH_PAGES: List[Target] = [
    Target(
        "rews-toolkit",
        "REWS Regulatory & Ethics Toolkit",
        "https://www.ga4gh.org/genomic-data-toolkit/regulatory-ethics-toolkit/",
        "data/corpus/P0/rews-regulatory-ethics-toolkit.txt",
        min_words=300,
    ),
    Target(
        "gdpr-primer",
        "GA4GH GDPR Forum announcement",
        "https://www.ga4gh.org/news_item/introducing-the-ga4gh-gdpr-and-international-health-data-sharing-forum/",
        "data/corpus/P1/gdpr-genomic-research-primer.txt",
        min_words=200,
    ),
    Target(
        "gdpr-consent",
        "GDPR Brief — broad consent",
        "https://www.ga4gh.org/news_item/gdpr-brief-is-consent-for-genomic-and-health-related-research-specific-enough-to-constitute-a-valid-consent-under-the-gdpr/",
        "data/corpus/P1/gdpr-consent-broad-genomic-research.txt",
        must_contain=["broad consent"],
        min_words=400,
    ),
    Target(
        "gdpr-dpia",
        "GDPR Brief — DPIA",
        "https://www.ga4gh.org/news_item/gdpr-brief-the-data-protection-impact-assessment-and-genomic-health-research/",
        "data/corpus/P1/gdpr-dpia-genomic-research.txt",
        must_contain=["impact assessment"],
        min_words=400,
    ),
    Target(
        "mrcg",
        "GA4GH Machine Readable Consent Guidance",
        "https://www.ga4gh.org/product/machine-readable-consent-guidance/",
        "data/corpus/P1/ga4gh-mrcg-consent-duo.txt",
        min_words=300,
    ),
    Target(
        "duo",
        "GA4GH Data Use Ontology",
        "https://www.ga4gh.org/product/data-use-ontology-duo/",
        "data/corpus/P1/ga4gh-duo-data-use-ontology.txt",
        min_words=300,
    ),
    Target(
        "gdpr-transfers",
        "GDPR Brief — international transfers",
        "https://www.ga4gh.org/news_item/how-can-researchers-approach-international-data-transfers-under-the-gdpr/",
        "data/corpus/P1/gdpr-international-transfers.txt",
        must_contain=["transfer"],
        min_words=400,
    ),
    Target(
        "gdpr-secondary",
        "GDPR Brief — secondary use",
        "https://www.ga4gh.org/news_item/finding-a-route-out-of-the-impasse/",
        "data/corpus/P1/gdpr-secondary-use.txt",
        min_words=400,
    ),
    Target(
        "gdpr-art9",
        "GDPR Brief — genetic data as special category",
        "https://www.ga4gh.org/news_item/what-specific-protections-apply-to-health-related-genetic-or-biometric-data/",
        "data/corpus/P1/gdpr-genetic-data-special-category.txt",
        min_words=400,
    ),
    Target(
        "gdpr-withdrawal",
        "GDPR Brief — withdrawal of consent",
        "https://www.ga4gh.org/news_item/gdpr-brief-withdrawing-consent-to-data-processing-under-the-gdpr/",
        "data/corpus/P1/gdpr-withdrawal-consent.txt",
        must_contain=["withdraw"],
        min_words=400,
    ),
]

ALL_TARGETS: List[Target] = TARGETS + GA4GH_PAGES


def _get(url: str, accept: Optional[Dict[str, str]] = None, timeout: int = 120) -> bytes:
    headers = {"User-Agent": UA}
    if accept:
        headers.update(accept)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "big5", "cp950", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_xhtml(raw: str) -> str:
    doc = LH.fromstring(raw.encode("utf-8"))
    for bad in doc.xpath("//script|//style"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    text = doc.text_content()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    # Drop the publisher's own file metadata, e.g. "L_2016119EN.01000101.xml 4.5.2016 EN"
    # and the Official Journal running line — neither is part of the Regulation.
    lines = [
        ln
        for ln in lines
        if not re.match(r"^L_\d+[A-Z]{2}\.\d+\.xml\b", ln)
        and not re.match(r"^Official Journal of the European Union\s*L?\s*[\d/]*$", ln)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_cellar(t: Target) -> str:
    raw = _decode(
        _get(t.url, {"Accept": "application/xhtml+xml", "Accept-Language": "eng"}, timeout=180)
    )
    return _clean_xhtml(raw)


def extract_html(t: Target) -> str:
    root = LH.fromstring(_decode(_get(t.url)))
    for bad in root.xpath("//script|//style|//nav|//header|//footer|//form|//noscript"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    node = root.xpath("//main") or root.xpath("//article") or [root]
    blocks, seen = [], set()
    for el in node[0].xpath(".//h1|.//h2|.//h3|.//h4|.//p|.//li"):
        text = " ".join(el.text_content().split())
        if not text or len(text) < 3 or BOILERPLATE.match(text):
            continue
        if text.strip().lower() in NAV_EXACT:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        if el.tag in ("h1", "h2", "h3", "h4"):
            blocks.append("\n" + text + "\n")  # blank-line delimited -> detect_headings
        elif el.tag == "li":
            blocks.append("- " + text)
        else:
            blocks.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(blocks)).strip()


def extract_moj_tw(t: Target) -> str:
    """
    Extract Taiwan statutes from the MOJ page's per-article structure.

    Each provision is a ``div.row`` holding ``div.col-no`` (the designation) and
    ``div.col-data`` (the text). Using that structure instead of splitting the page text on
    /Article \\d+/ matters: the earlier regex approach also fired on **cross-references**
    inside a provision — "referred to in Article 5, Paragraph 3 hereof" became a fake
    "Article 5" heading followed by a sentence fragment, so several designations appeared
    four times and real articles were shattered.
    """
    parts = []
    for url in t.url.split("|"):
        root = LH.fromstring(_decode(_get(url)))
        content = root.xpath("//div[contains(@class,'law-reg-content')]")
        if not content:
            raise RuntimeError(f"law-reg-content not found at {url}")

        blocks = []
        for node in content[0].xpath(".//h3 | .//div[contains(@class,'row')]"):
            if node.tag == "h3":  # chapter heading
                chapter = " ".join(node.text_content().split())
                if chapter:
                    blocks.append(f"\n{chapter}\n")
                continue
            no = node.xpath(".//div[contains(@class,'col-no')]")
            data = node.xpath(".//div[contains(@class,'col-data')]")
            if not no or not data:
                continue
            designation = " ".join(no[0].text_content().split()).rstrip(".")
            body = " ".join(data[0].text_content().split())
            if not designation or not body:
                continue
            # Blank-line delimited so detect_headings sees exactly one heading per article.
            blocks.append(f"\n{designation}\n\n{body}")

        if len(blocks) < 5:
            raise RuntimeError(f"only {len(blocks)} articles parsed from {url}")
        body_text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(blocks)).strip()
        parts.append(f"Source: {url}\n\n{body_text}")
        time.sleep(POLITE_DELAY_S)
    return "\n\n".join(parts)


EXTRACTORS: Dict[str, Callable[[Target], str]] = {
    "cellar": extract_cellar,
    "html": extract_html,
    "moj_tw": extract_moj_tw,
}


def validate(t: Target, text: str) -> List[str]:
    """Reasons this content must not be written. Empty list means it passed."""
    problems = []
    words = len(text.split())
    if words < t.min_words:
        problems.append(f"only {words} words, expected >= {t.min_words}")
    lowered = text.lower()
    for phrase in t.must_contain:
        if phrase.lower() not in lowered:
            problems.append(f"missing required phrase {phrase!r} — likely a table of contents")
    return problems


def fetch_one(t: Target, *, dry_run: bool = False) -> bool:
    out = ROOT / t.out
    if t.extractor == "binary":
        if dry_run:
            print(f"  would fetch  {t.key}")
            return True
        data = _get(t.url, timeout=180)
        if not data.startswith(b"%PDF"):
            print(f"  REJECT {t.key}: not a PDF ({len(data)} bytes)")
            return False
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"  ok     {t.key}  {len(data) // 1024} KB  -> {t.out}")
        return True

    if dry_run:
        print(f"  would fetch  {t.key}")
        return True

    try:
        body = EXTRACTORS[t.extractor](t)
    except Exception as exc:  # noqa: BLE001 — report and continue with other targets
        print(f"  FAIL   {t.key}: {str(exc)[:110]}")
        return False

    problems = validate(t, body)
    if problems:
        print(f"  REJECT {t.key}: {'; '.join(problems)}")
        print("         nothing written — a table of contents pollutes retrieval")
        return False

    header = f"Source: {t.url.split('|')[0]}\n\n{t.title}\n\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + body + "\n", encoding="utf-8")
    print(f"  ok     {t.key}  {len(body.split()):6d} words  -> {t.out}")
    return True


def check_existing() -> int:
    failures = 0
    for t in ALL_TARGETS:
        path = ROOT / t.out
        if not path.exists():
            print(f"  MISSING {t.key}  {t.out}")
            failures += 1
            continue
        if t.extractor == "binary":
            print(f"  ok      {t.key}  {path.stat().st_size // 1024} KB")
            continue
        problems = validate(t, path.read_text(encoding="utf-8", errors="replace"))
        if problems:
            print(f"  BAD     {t.key}: {'; '.join(problems)}")
            failures += 1
        else:
            print(f"  ok      {t.key}")
    return failures


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--only", action="append", metavar="KEY", help="Fetch only these targets.")
    p.add_argument("--list", action="store_true", help="List targets and exit.")
    p.add_argument("--check", action="store_true", help="Validate files already on disk.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be fetched.")
    args = p.parse_args(argv)

    if args.list:
        for t in ALL_TARGETS:
            print(f"  {t.key:16s} {t.out}")
            print(f"  {'':16s} {t.title}")
        return 0

    if args.check:
        failures = check_existing()
        print(f"\n{len(ALL_TARGETS) - failures}/{len(ALL_TARGETS)} targets valid")
        return 1 if failures else 0

    selected = [t for t in ALL_TARGETS if not args.only or t.key in args.only]
    if not selected:
        print(f"No target matched {args.only}. Use --list.", file=sys.stderr)
        return 2

    ok = 0
    for t in selected:
        if fetch_one(t, dry_run=args.dry_run):
            ok += 1
        time.sleep(POLITE_DELAY_S)

    print(f"\n{ok}/{len(selected)} targets written.")
    print("Re-index with:  python -m src.main ingest-manifest --reset --force")
    return 0 if ok == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
