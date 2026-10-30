"""
Fetch the consent-form documents used as queries in the consent → provision benchmark.

Each target records where the document came from and the reuse terms as stated by the
publisher, so the benchmark can be rebuilt from source and every document's licence can be
checked before redistribution. Files are downloaded into their own directory under
``data/consent_benchmark/raw/<doc_id>/`` and converted to plain text at
``data/consent_benchmark/<doc_id>.txt``. Only targets marked ``redistributable`` are meant
to be committed; the others are fetch-only.

Every fetch is validated before it is kept: a target declares required phrases and a
minimum word count, so a landing page or an error page is rejected rather than labelled.

    python -I tools/experiments/fetch_consent_docs.py --list
    python -I tools/experiments/fetch_consent_docs.py            # fetch + convert everything
    python -I tools/experiments/fetch_consent_docs.py --only us-all-of-us-consent-to-join
    python -I tools/experiments/fetch_consent_docs.py --check    # re-validate what is on disk

Run with ``-I``: the downloaded files are untrusted input and the converters read them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "data", "consent_benchmark")
RAW_DIR = os.path.join(OUT_DIR, "raw")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")
USER_AGENT = "GA4GH-RegBot consent benchmark fetcher (research use; contact via repository)"

TARGETS: List[Dict[str, Any]] = [
    {
        "doc_id": "us-nih-osp-secondary-research-sample",
        "title": "NIH OSP — Informed Consent for Secondary Research with Data and Biospecimens: "
        "Points to Consider and Sample Language (May 2022)",
        "url": "https://osp.od.nih.gov/wp-content/uploads/Informed-Consent-Resource-for-Secondary-Research-with-Data-and-Biospecimens.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US",
        "licence": "US federal government work; no licence stated (public domain)",
        "redistributable": True,
        "text_type": "guidance with sample consent language",
        "must_contain": ["secondary research", "consent"],
        "min_words": 1500,
    },
    {
        "doc_id": "us-nhgri-gds-sample-language",
        "title": "NHGRI — Genomic Data Sharing Policy: sample informed consent language",
        "url": "https://www.genome.gov/about-genomics/policy-issues/Informed-Consent/GDS-policy-sample-language",
        "kind": "html",
        "language": "en",
        "origin": "US",
        "licence": "NHGRI web content is in the public domain unless otherwise indicated",
        "redistributable": True,
        "text_type": "sample consent language",
        "must_contain": ["consent", "genomic"],
        "min_words": 1200,
    },
    {
        "doc_id": "us-nih-irb-consent-library",
        "title": "NIH IRB Consent Library v18 (OHSRP, February 2026)",
        "url": "https://irbo.nih.gov/documents/306/2026_02_05_Consent_Library_v18.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US",
        "licence": "US federal government work; no licence stated (public domain)",
        "redistributable": True,
        "text_type": "consent template library (genomic sections used)",
        "must_contain": ["consent", "genetic"],
        "min_words": 5000,
    },
    {
        "doc_id": "us-all-of-us-consent-to-join",
        "title": "All of Us Research Program — Consent to Join (English)",
        "url": "https://www.genome.gov/sites/default/files/media/files/2022-01/Consent_to_Join_AoU_English.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US",
        "licence": "Hosted by NHGRI as a sample document; drafted for NIH by VUMC; "
        "public-domain status likely but not confirmed — attribute",
        "redistributable": False,
        "text_type": "participant-facing consent form",
        "must_contain": ["All of Us", "consent"],
        "min_words": 2500,
    },
    {
        "doc_id": "us-1000-genomes-consent",
        "title": "1000 Genomes Project — sample consent form",
        "url": "https://www.genome.gov/sites/default/files/media/files/2022-01/1000_Genomes_Project_Consent.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US / international",
        "licence": "Hosted by NHGRI as a sample document; attribute",
        "redistributable": False,
        "text_type": "participant-facing consent form",
        "must_contain": ["1000 Genomes", "consent"],
        "min_words": 1500,
    },
    {
        "doc_id": "us-emerge-consent",
        "title": "eMERGE Network — consent and community consultation template",
        "url": "https://www.genome.gov/sites/default/files/media/files/2022-01/eMERGE_consent.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US",
        "licence": "Hosted by NHGRI as a sample document; consortium-authored; attribute",
        "redistributable": False,
        "text_type": "participant-facing consent template",
        "must_contain": ["consent"],
        "min_words": 2000,
    },
    {
        "doc_id": "us-gtex-live-donor-consent",
        "title": "GTEx — live donor informed consent template",
        "url": "https://www.genome.gov/sites/default/files/media/files/2022-01/GTEx_Live_Donor_Informed_Consent.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "US",
        "licence": "Hosted by NHGRI as a sample document; attribute",
        "redistributable": False,
        "text_type": "participant-facing consent form",
        "must_contain": ["consent"],
        "min_words": 400,
    },
    {
        "doc_id": "us-beskow-simplified-biobank-consent",
        "title": "Beskow et al. (2010) — simplified consent form for biobanking (PLoS ONE S1)",
        "url": "https://doi.org/10.1371/journal.pone.0013302.s001",
        "kind": "doc",
        "language": "en",
        "origin": "US",
        "licence": "CC BY (PLoS ONE open-access article supplement)",
        "redistributable": True,
        "text_type": "participant-facing consent form",
        "must_contain": ["consent"],
        "min_words": 600,
    },
    {
        "doc_id": "eu-uppsala-biobank-registry-consent-template",
        "title": "Uppsala University CRB — Informed consent guide and template for biobank and "
        "registry-based research",
        "url": "https://zenodo.org/api/records/3928446/files/Informed-Consent-Guide.pdf/content",
        "kind": "pdf",
        "language": "en",
        "origin": "EU (Sweden)",
        "licence": "CC BY 4.0 (Zenodo record 3928446)",
        "redistributable": True,
        "text_type": "consent template with guidance",
        "must_contain": ["consent", "biobank"],
        "min_words": 1000,
    },
    {
        "doc_id": "ee-estonian-biobank-gene-donor-consent",
        "title": "Estonian Biobank — Gene Donor Consent Form (annex to Regulation No 39 of 2019)",
        "url": "https://genomics.ut.ee/sites/default/files/2022-01/Gene%20donor%20consent%20form_2019_EN.pdf",
        "kind": "pdf",
        "language": "en",
        "origin": "EU (Estonia)",
        "licence": "Annex to a ministerial regulation; no licence stated on page",
        "redistributable": False,
        "text_type": "participant-facing consent form",
        "must_contain": ["gene donor"],
        "min_words": 600,
    },
    {
        "doc_id": "kr-bioethics-form-34-research-consent",
        "title": "Korea — Bioethics and Safety Act Enforcement Rule, Form 34: consent to research "
        "on human materials (as used by the National Biobank of Korea)",
        "url": "https://biobank.nih.go.kr/cadaver/static/file_en/collection_deposit/coll_depo_34.pdf",
        "kind": "pdf",
        "language": "ko",
        "origin": "KR",
        "licence": "Statutory form; Korean Copyright Act Art. 7 excludes laws and rules",
        "redistributable": True,
        "text_type": "participant-facing consent form (statutory)",
        "must_contain": ["동의"],
        "min_words": 150,
    },
    {
        "doc_id": "jp-amed-model-explanation-text",
        "title": "AMED — model wording for research explanation documents (data sharing)",
        "url": "https://www.amed.go.jp/content/000140372.pdf",
        "kind": "pdf",
        "language": "ja",
        "origin": "JP",
        "licence": "Reproduction permitted with attribution; commercial use requires AMED approval",
        "redistributable": False,
        "text_type": "model explanation/consent text",
        "must_contain": ["同意"],
        "min_words": 800,
    },
    {
        "doc_id": "tw-mohw-biobank-consent-template",
        "title": "Taiwan MOHW — 人體生物資料庫參與者同意書參考格式 (biobank participant consent "
        "reference template, DOCX attachment of dep.mohw.gov.tw/DOMA/cp-3133-12827-106.html)",
        "url": "https://www.mohw.gov.tw/dl-96426-009007ef-05ad-4896-af0d-33fd9c5e1854.html",
        "kind": "docx",
        "language": "zh",
        "origin": "TW",
        "licence": "Taiwan Open Government Data Licence v1 (attribution required)",
        "redistributable": True,
        "text_type": "participant-facing consent template",
        "must_contain": ["同意"],
        "min_words": 300,
    },
]


def _word_count(text: str) -> int:
    latin = len(re.findall(r"[A-Za-z0-9]+", text))
    cjk = len(re.findall(r"[㐀-鿿぀-ヿ가-힯]", text))
    return latin + cjk // 2


def _download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _pdf_text(path: str) -> str:
    from pypdf import PdfReader

    pages = []
    for page in PdfReader(path).pages:
        pages.append(page.extract_text() or "")
    return "\n\f\n".join(pages)


def _html_text(path: str) -> str:
    import lxml.html

    with open(path, "rb") as f:
        doc = lxml.html.fromstring(f.read())
    for bad in doc.xpath("//script|//style|//nav|//header|//footer|//noscript"):
        bad.getparent().remove(bad)
    main = doc.xpath("//main") or doc.xpath("//article") or doc.xpath("//body")
    text = main[0].text_content() if main else doc.text_content()
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _office_text(path: str) -> str:
    """Convert .doc/.docx/.odt via macOS textutil, falling back to LibreOffice."""
    out = path + ".txt"
    if shutil.which("textutil") and not path.lower().endswith(".odt"):
        subprocess.run(["textutil", "-convert", "txt", "-output", out, path], check=True)
    else:
        soffice = shutil.which("soffice")
        if not soffice:
            raise RuntimeError("neither textutil nor soffice is available for office documents")
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                os.path.dirname(path),
                path,
            ],
            check=True,
            capture_output=True,
        )
        out = os.path.splitext(path)[0] + ".txt"
    with open(out, encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract(kind: str, path: str) -> str:
    if kind == "pdf":
        return _pdf_text(path)
    if kind == "html":
        return _html_text(path)
    if kind in ("doc", "docx", "odt"):
        return _office_text(path)
    raise ValueError(kind)


def _validate(target: Dict[str, Any], text: str) -> List[str]:
    problems = []
    words = _word_count(text)
    if words < int(target.get("min_words", 0)):
        problems.append(f"only {words} words (< {target['min_words']})")
    low = text.lower()
    for phrase in target.get("must_contain") or []:
        if phrase.lower() not in low:
            problems.append(f"missing phrase {phrase!r}")
    return problems


def _filename_for(target: Dict[str, Any]) -> str:
    ext = {"pdf": "pdf", "html": "html", "doc": "doc", "docx": "docx", "odt": "odt"}[target["kind"]]
    return f"{target['doc_id']}.{ext}"


def fetch_one(target: Dict[str, Any], *, check_only: bool, dry_run: bool) -> Dict[str, Any]:
    raw_dir = os.path.join(RAW_DIR, target["doc_id"])
    raw_path = os.path.join(raw_dir, _filename_for(target))
    txt_path = os.path.join(OUT_DIR, f"{target['doc_id']}.txt")
    record: Dict[str, Any] = {
        k: v for k, v in target.items() if k not in ("must_contain", "min_words")
    }
    if dry_run:
        record["status"] = "would fetch" if not os.path.exists(raw_path) else "on disk"
        return record
    if not check_only:
        os.makedirs(raw_dir, exist_ok=True)
        for stale in os.listdir(raw_dir):
            os.remove(os.path.join(raw_dir, stale))
        try:
            _download(target["url"], raw_path)
        except Exception as exc:  # noqa: BLE001 — report and continue with the next target
            record["status"] = f"download failed: {exc}"
            return record
    if not os.path.exists(raw_path):
        record["status"] = "not on disk"
        return record
    try:
        text = _extract(target["kind"], raw_path)
    except Exception as exc:  # noqa: BLE001
        record["status"] = f"extraction failed: {exc}"
        return record
    problems = _validate(target, text)
    record["sha256"] = _sha256(raw_path)
    record["words"] = _word_count(text)
    if problems:
        record["status"] = "rejected: " + "; ".join(problems)
        if os.path.exists(txt_path):
            os.remove(txt_path)
        return record
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    record["status"] = "ok"
    record["text_path"] = os.path.relpath(txt_path, ROOT)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", action="append")
    ap.add_argument("--check", action="store_true", help="validate files already on disk")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    targets = [t for t in TARGETS if not args.only or t["doc_id"] in set(args.only)]
    if args.list:
        for t in targets:
            flag = "redistributable" if t["redistributable"] else "fetch-only"
            print(f"{t['doc_id']:<48} {t['language']:<3} {flag:<15} {t['url']}")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    records = []
    failures = 0
    for t in targets:
        rec = fetch_one(t, check_only=args.check, dry_run=args.dry_run)
        records.append(rec)
        ok = rec["status"] in ("ok", "on disk", "would fetch")
        failures += 0 if ok else 1
        print(
            f"{'OK ' if ok else 'ERR'} {t['doc_id']:<48} {rec.get('words', ''):>6} {rec['status']}"
        )
    if not args.dry_run:
        existing: Dict[str, Any] = {}
        if os.path.exists(MANIFEST):
            with open(MANIFEST, encoding="utf-8") as f:
                existing = {r["doc_id"]: r for r in json.load(f).get("documents", [])}
        for rec in records:
            existing[rec["doc_id"]] = rec
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump({"documents": list(existing.values())}, f, indent=1, ensure_ascii=False)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
