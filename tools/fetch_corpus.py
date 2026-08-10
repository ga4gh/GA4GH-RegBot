#!/usr/bin/env python3
"""
Rebuild the primary-source corpus under ``data/corpus/`` from its official publishers.

Without this, the corpus is a set of opaque files nobody can regenerate or audit. Run it
from the repository root:

    python tools/fetch_corpus.py --list          # show targets, fetch nothing
    python tools/fetch_corpus.py --only gdpr     # refresh one target
    python tools/fetch_corpus.py                 # refresh everything
    python tools/fetch_corpus.py --check         # validate files already on disk

**Every fetch is validated before it is written**, PDFs included: the extracted text must
carry each `must_contain` phrase and clear `min_words`, or nothing is written. An earlier
run silently captured Singapore and Japan *tables of contents* instead of the statutes, and
a table of contents is worse than nothing in a retrieval corpus — it matches query
vocabulary and states no rule.

Two records this file used to carry are corrected. The Singapore failure was diagnosed by
the absence of "shall not", which was never a valid test: the 2020 Revised Edition converted
"shall" to "must" throughout, so the full statute has none either. And Hong Kong and Korea
were listed as unfetchable JavaScript shells. Hong Kong e-Legislation is one, but the
Privacy Commissioner publishes the Ordinance itself; Korea's KLRI `lawView.do` is merely a
frameset wrapper whose iframe target is server-rendered. Both are fetched here now.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional

from lxml import etree as LET
from lxml import html as LH

# Several official PDFs contain malformed inline-image streams although their text layer
# is intact. Retain pypdf errors, but suppress image-decoder warnings after the strict
# phrase and length validation below has established that the text is usable.
logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
POLITE_DELAY_S = 1.5
RETRIEVED = date.today().isoformat()

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
    #: CJK statutes do not delimit lexical words with spaces. A character floor provides
    #: the same protection against accidentally indexing a contents page for those texts.
    min_chars: int = 0
    #: Drop everything before the first occurrence of this marker. Some publishers print a
    #: full table of contents above the operative text in the same document; indexed, it
    #: becomes chunks of bare headings that match query vocabulary and state no rule.
    strip_before: str = ""
    #: Drop publisher footer/navigation beginning at this target-specific marker.
    strip_after: str = ""
    note: str = ""


def _drive(file_id: str) -> str:
    """
    Direct-download URL for a Google Drive file.

    Every GA4GH policy PDF is hosted on Drive rather than on ga4gh.org: the ``/document/``
    and ``/product/`` pages are JavaScript wrappers whose only payload is a Drive link, so
    fetching the page itself yields no policy text.
    """
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _gdoc_pdf(document_id: str) -> str:
    """PDF export URL for a public native Google Doc."""
    return f"https://docs.google.com/document/d/{document_id}/export?format=pdf"


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
    Target(
        key="ehds",
        title="Regulation (EU) 2025/327 on the European Health Data Space (EHDS)",
        url="https://publications.europa.eu/resource/celex/32025R0327",
        out="data/corpus/P1/european-health-data-space-regulation-2025-327.txt",
        extractor="cellar",
        must_contain=[
            "secondary use of electronic health data",
            "health data access body",
            "Article 53",
        ],
        min_words=50000,
        note="EU Publications Office CELLAR, official English text. In force since "
        "26 March 2025; most secondary-use provisions apply from 26 March 2029.",
    ),
    Target(
        key="eu-data-governance-act",
        title="Regulation (EU) 2022/868 on European data governance (Data Governance Act)",
        url="https://publications.europa.eu/resource/celex/32022R0868",
        out="data/corpus/P1/eu-data-governance-act-2022-868.txt",
        extractor="cellar",
        must_contain=["data altruism organisation", "Article 31", "protected data"],
        min_words=25000,
        note="EU Publications Office CELLAR, official English text; applicable since "
        "24 September 2023.",
    ),
    Target(
        key="eu-data-act",
        title="Regulation (EU) 2023/2854 on fair access to and use of data (Data Act)",
        url="https://publications.europa.eu/resource/celex/32023R2854",
        out="data/corpus/P1/eu-data-act-2023-2854.txt",
        extractor="cellar",
        must_contain=["making data available", "Article 32", "Article 50"],
        min_words=30000,
        note="EU Publications Office CELLAR, official English text; applicable since "
        "12 September 2025.",
    ),
    Target(
        key="eu-clinical-trials-regulation",
        title="Regulation (EU) No 536/2014 on clinical trials on medicinal products",
        url="https://publications.europa.eu/resource/celex/32014R0536",
        out="data/corpus/P1/eu-clinical-trials-regulation-536-2014.txt",
        extractor="cellar",
        must_contain=["Article 28", "informed consent", "Clinical trials on minors"],
        min_words=35000,
        note="EU Publications Office CELLAR, official English text; applicable since "
        "31 January 2022.",
    ),
    Target(
        key="who-human-genome-data-guidance",
        title="WHO Guidance for human genome data collection, access, use and sharing",
        url=(
            "https://iris.who.int/server/api/core/bitstreams/"
            "c32ba78e-de45-416a-a5ae-3863b93e4628/content"
        ),
        out="data/corpus/P1/who-human-genome-data-guidance-2024.pdf",
        extractor="binary",
        must_contain=[
            "Guidance for human genome data collection, access, use and sharing",
            "informed consent",
        ],
        min_words=4500,
        note="WHO normative guidance, published 20 November 2024 (ISBN 978-92-4-010214-9).",
    ),
    Target(
        key="oecd-health-data-governance",
        title="OECD Recommendation of the Council on Health Data Governance",
        url="https://legalinstruments.oecd.org/public/doc/348/348.en.pdf",
        out="data/corpus/P1/oecd-health-data-governance-recommendation.pdf",
        extractor="binary",
        must_contain=[
            "Recommendation of the Council on Health Data Governance",
            "withdraw consent",
        ],
        min_words=3500,
        note="OECD/LEGAL/0433, adopted 13 December 2016; current official instrument PDF.",
    ),
    Target(
        key="oecd-biobanks-genetic-databases",
        title="OECD Recommendation on Human Biobanks and Genetic Research Databases",
        url="https://legalinstruments.oecd.org/api/print?ids=218&lang=en",
        out="data/corpus/P1/oecd-human-biobanks-genetic-research-databases.pdf",
        extractor="binary",
        must_contain=[
            "GUIDELINES ON HUMAN BIOBANKS AND GENETIC RESEARCH DATABASES",
            "right to withdraw",
        ],
        min_words=6000,
        note="OECD/LEGAL/0375, adopted 22 October 2009; current official instrument PDF.",
    ),
    Target(
        key="unesco-human-genetic-data",
        title="UNESCO International Declaration on Human Genetic Data",
        url=(
            "https://www.unesco.org/en/legal-affairs/"
            "international-declaration-human-genetic-data?hub=66535"
        ),
        out="data/corpus/P1/unesco-international-declaration-human-genetic-data.txt",
        extractor="html",
        must_contain=[
            "Prior, free, informed and express consent",
            "cross-border flow of human genetic data",
        ],
        min_words=3500,
        strip_before="The General Conference,",
        note="Official UNESCO legal-instrument text, adopted 16 October 2003.",
    ),
    Target(
        key="unesco-human-genome-rights",
        title="UNESCO Universal Declaration on the Human Genome and Human Rights",
        url=(
            "https://www.unesco.org/en/legal-affairs/"
            "universal-declaration-human-genome-and-human-rights"
        ),
        out="data/corpus/P1/unesco-universal-declaration-human-genome-human-rights.txt",
        extractor="html",
        must_contain=[
            "No one shall be subjected to discrimination based on genetic characteristics",
            "Research, treatment or diagnosis affecting an individual's genome",
        ],
        min_words=1800,
        strip_before="The General Conference,",
        note="Official UNESCO legal-instrument text, adopted 11 November 1997 and endorsed "
        "by the UN General Assembly in 1998.",
    ),
    Target(
        key="unesco-bioethics-human-rights",
        title="UNESCO Universal Declaration on Bioethics and Human Rights",
        url=(
            "https://www.unesco.org/en/legal-affairs/"
            "universal-declaration-bioethics-and-human-rights?hub=66535"
        ),
        out="data/corpus/P1/unesco-universal-declaration-bioethics-human-rights.txt",
        extractor="html",
        must_contain=["Privacy and confidentiality", "prior, free and informed consent"],
        min_words=2500,
        strip_before="The General Conference,",
        note="Official UNESCO legal-instrument text, adopted 19 October 2005.",
    ),
    Target(
        key="coe-oviedo-convention",
        title="Council of Europe Convention on Human Rights and Biomedicine (ETS No. 164)",
        url="https://rm.coe.int/168007cf98",
        out="data/corpus/P1/coe-oviedo-convention-ets-164.pdf",
        extractor="binary",
        must_contain=[
            "Predictive genetic tests",
            "Protection of persons undergoing research",
            "free and informed consent",
        ],
        min_words=2500,
        note="Official English treaty text published by the Council of Europe; opened for "
        "signature 4 April 1997 and in force since 1 December 1999.",
    ),
    Target(
        key="coe-biomedical-research-protocol",
        title="Council of Europe Additional Protocol concerning Biomedical Research (CETS No. 195)",
        url="https://rm.coe.int/1680083709",
        out="data/corpus/P1/coe-biomedical-research-protocol-cets-195.pdf",
        extractor="binary",
        must_contain=[
            "concerning Biomedical Research",
            "Consent",
            "independent examination of its ethical acceptability",
        ],
        min_words=4500,
        note="Official English treaty text published by the Council of Europe; in force "
        "since 1 September 2007.",
    ),
    Target(
        key="coe-genetic-testing-protocol",
        title="Council of Europe Additional Protocol concerning Genetic Testing for Health Purposes",
        url="https://rm.coe.int/1680084824",
        out="data/corpus/P1/coe-genetic-testing-health-purposes-cets-203.pdf",
        extractor="binary",
        must_contain=[
            "Genetic counselling",
            "predictive genetic tests",
            "entitled to know any information collected",
        ],
        min_words=2500,
        note="Official English CETS No. 203 treaty text published by the Council of Europe; "
        "in force since 1 July 2018.",
    ),
    Target(
        key="coe-biological-materials-recommendation",
        title="Council of Europe Recommendation CM/Rec(2016)6 on research on biological materials",
        url=(
            "https://rm.coe.int/CoERMPublicCommonSearchServices/DisplayDCTMContent"
            "?documentId=090000168064e8ff"
        ),
        out="data/corpus/P1/coe-recommendation-2016-6-biological-materials.txt",
        extractor="mixed",
        must_contain=[
            "research on biological materials of human origin",
            "storage for future research purposes",
            "independent examination",
        ],
        min_words=3500,
        note="Official Committee of Ministers text, adopted 11 May 2016; includes the "
        "recommendation and revised biobank/research-material principles.",
    ),
    Target(
        key="coe-health-data-recommendation",
        title="Council of Europe Recommendation CM/Rec(2019)2 on health-related data",
        url=(
            "https://rm.coe.int/CoERMPublicCommonSearchServices/DisplayDCTMContent"
            "?documentId=090000168093b26e"
        ),
        out="data/corpus/P1/coe-recommendation-2019-2-health-related-data.pdf",
        extractor="binary",
        must_contain=[
            "Scientific research",
            "Transborder flows of health-related data",
            "appropriate level of data protection",
        ],
        min_words=5000,
        note="Official English Committee of Ministers recommendation, adopted 27 March 2019.",
    ),
    Target(
        key="who-human-genome-editing-governance",
        title="WHO Human genome editing: a framework for governance",
        url=(
            "https://iris.who.int/server/api/core/bitstreams/"
            "cdcfed77-66d5-46c3-9073-4018a3d2c48d/content"
        ),
        out="data/corpus/P1/who-human-genome-editing-governance-2021.pdf",
        extractor="binary",
        must_contain=[
            "HUMAN GENOME EDITING: A FRAMEWORK FOR GOVERNANCE",
            "Values and principles",
            "heritable human genome editing",
        ],
        min_words=16000,
        note="WHO governance framework, published 12 July 2021; CC BY-NC-SA 3.0 IGO.",
    ),
    Target(
        key="eu-standard-contractual-clauses",
        title="Commission Implementing Decision (EU) 2021/914 on standard contractual clauses",
        url="https://publications.europa.eu/resource/celex/32021D0914",
        out="data/corpus/P1/eu-standard-contractual-clauses-2021-914.txt",
        extractor="cellar",
        must_contain=[
            "STANDARD CONTRACTUAL CLAUSES",
            "Clause 14",
            "local laws and practices affecting compliance with the Clauses",
        ],
        min_words=16000,
        note="Official English text from the EU Publications Office CELLAR; applies to "
        "transfers of personal data to third countries under the GDPR.",
    ),
    Target(
        key="edpb-consent-guidelines",
        title="EDPB Guidelines 05/2020 on consent under Regulation 2016/679",
        url=(
            "https://www.edpb.europa.eu/system/files/documents/files/file1/"
            "edpb_guidelines_202005_consent_en.pdf"
        ),
        out="data/corpus/P1/edpb-guidelines-05-2020-consent.txt",
        extractor="pdf_text_cli",
        must_contain=["Elements of valid consent", "Scientific research", "Withdrawal of consent"],
        min_words=14000,
        note="Official EDPB Guidelines 05/2020, version 1.1 adopted 4 May 2020.",
    ),
    Target(
        key="edpb-clinical-trials-gdpr-opinion",
        title="EDPB Opinion 3/2019 on the Clinical Trials Regulation and GDPR",
        url=(
            "https://www.edpb.europa.eu/system/files/documents/files/file1/"
            "edpb_opinionctrq_a_final_en.pdf"
        ),
        out="data/corpus/P1/edpb-opinion-3-2019-clinical-trials-gdpr.pdf",
        extractor="binary",
        must_contain=[
            "processing of personal data in the context of clinical trials",
            "secondary use",
            "informed consent",
        ],
        min_words=3500,
        note="Official EDPB Opinion 3/2019, adopted 23 January 2019.",
    ),
    Target(
        key="ga4gh-diversity-in-datasets",
        title="GA4GH Diversity in Datasets Policy",
        url=_drive("12ibnVwotkWa0k3MSm4ku3zodKRRB_h3Y"),
        out="data/corpus/P0/ga4gh-diversity-in-datasets-policy.pdf",
        extractor="binary",
        must_contain=[
            "Diversity in Datasets",
            "diversity in data as a means to achieve ethical ends",
        ],
        min_words=2500,
        note="Official GA4GH policy, current v2.4 product text.",
    ),
    Target(
        key="ga4gh-consent-rare-disease",
        title="GA4GH Model Consent Clauses for Rare Disease Research",
        url=_drive("1yfVo2LBTHL3mXCe-hYk9lDcEJZYJi8HM"),
        out="data/corpus/P1/ga4gh-consent-clauses-rare-disease.pdf",
        extractor="binary",
        must_contain=["Model Consent Clauses for Rare Disease Research", "rare disease"],
        min_words=2500,
        note="Official sixth component of the GA4GH Consent Toolkit.",
    ),
    Target(
        key="ga4gh-gedi",
        title="GA4GH Genetic Discrimination: Implications for Data Sharing Projects",
        url=_drive("1ytdibtFZ5sLq3mffonVMeIjmfujkvDyN"),
        out="data/corpus/P0/ga4gh-genetic-discrimination-data-sharing-projects.pdf",
        extractor="binary",
        must_contain=[
            "Genetic Discrimination: Implications for Data Sharing Projects",
            "data sharing projects",
        ],
        min_words=1200,
        note="Official GA4GH GEDI policy tool; complements the later position statement.",
    ),
    Target(
        key="ga4gh-genomic-newborn-screening",
        title="GA4GH Genomic sequencing in newborn screening policy tool",
        url=_gdoc_pdf("1pFhY8nwlmlB7yxDaRapN9wmOmKRVGjfJjFpCa-Xe8A4"),
        out="data/corpus/P0/ga4gh-genomic-newborn-screening-policy-tool.pdf",
        extractor="binary",
        must_contain=[
            "genomic sequencing in newborn screening",
            "ethical, legal and social implications",
        ],
        min_words=4000,
        note="Official GA4GH policy tool v1.0.0, approved 3 February 2026.",
    ),
    Target(
        key="ga4gh-covid-responsible-sharing",
        title="GA4GH Responsible data sharing for the COVID-19 pandemic",
        url=_gdoc_pdf("1wK_NoNYXKy0ttTQ-ySHh3ZRpvPrLV4uPwV8FSq6BQ60"),
        out="data/corpus/P0/ga4gh-covid-19-responsible-data-sharing.pdf",
        extractor="binary",
        must_contain=[
            "Responsible Data Sharing to Respond to the COVID-19 Pandemic",
            "privacy and data protection",
        ],
        min_words=1800,
        note="Official GA4GH ethical and legal considerations, current v3.0 product text.",
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
        key="tw-human-subjects",
        title="Taiwan — Human Subjects Research Act (official English)",
        url="https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=L0020176",
        out="data/corpus/P2/TW/human-subjects-research-act.txt",
        extractor="moj_tw",
        must_contain=[
            "provided for specified research purposes overseas",
            "Institutional Review Board",
            "may revoke their consent",
        ],
        min_words=2200,
        note="Ministry of Justice official English translation, amended 2 January 2019.",
    ),
    Target(
        key="ga4gh-psp",
        title="GA4GH Data Privacy and Security Policy v2.0",
        url=_drive("1QBZPO3eSJbtEcsnfaeZem1DE-z4yuhtl"),
        out="data/corpus/P0/ga4gh-data-privacy-security-policy-v2.txt",
        extractor="pdf_text",
        must_contain=[
            "Version POL 001/v. 2.0: August 2019",
            "Every system that accesses, stores, or transmits data",
        ],
        min_words=4000,
        note="Current v2.0 PDF linked from the GA4GH product page; replaces v1.0 (2015).",
    ),
    Target(
        key="ga4gh-clinically-actionable-results",
        title="GA4GH Policy on Clinically Actionable Genomic Research Results",
        url=_drive("1NVigcEqCs1TmOfZGyQneVTROkEE0FuP8"),
        out="data/corpus/P0/ga4gh-policy-clinically-actionable-results.txt",
        extractor="pdf_text",
        must_contain=[
            "POL 007 v1.0: June 24 2021",
            "clinically actionable genomic research results",
        ],
        min_words=4000,
        note="POL 007 / v1.0, approved 24 June 2021.",
    ),
    Target(
        key="ga4gh-engagement-framework",
        title="GA4GH Framework for Involving and Engaging Participants, Patients and Publics",
        url=_drive("1G9-cpYe20UU_auDXQN1iUJMgoH2t7HQx"),
        out="data/corpus/P0/ga4gh-participant-patient-public-engagement-framework.txt",
        extractor="pdf_text",
        must_contain=[
            "POL 006/ v1.0: July 2021",
            "involving and engaging participants, patients and publics",
        ],
        min_words=4200,
        note="POL 006 / v1.0, July 2021.",
    ),
    Target(
        key="ga4gh-data-sharing-lexicon",
        title="GA4GH Data Sharing Lexicon",
        url=_drive("1Np2btBz7CQZeOcsna7tiDyK8wIVNW8uV"),
        out="data/corpus/P0/ga4gh-data-sharing-lexicon.txt",
        extractor="pdf_text",
        must_contain=["GA4GH Data Sharing Lexicon", "Controlled/ Managed/"],
        min_words=3000,
        note="Revised GA4GH product, February 2025.",
    ),
    Target(
        key="ga4gh-model-daa",
        title="GA4GH Model Data Access Agreement Clauses",
        url=_drive("1S_muUQg69npWLd4EIkYuqfLEKprgh8CG"),
        out="data/corpus/P0/ga4gh-model-data-access-agreement-clauses.txt",
        extractor="pdf_text",
        must_contain=[
            "Model Data Access Agreement",
            "external collaborator must first obtain approval from the Data Provider",
        ],
        min_words=3000,
        note="Official GA4GH product approved 19 November 2024.",
    ),
    Target(
        key="ga4gh-genetic-discrimination",
        title="GA4GH Position Statement on Genetic Discrimination",
        url=_gdoc_pdf("1ncab7gxSh4ubEeAUU10Pnzbjg8ga7i9mc2jh0MRDjTo"),
        out="data/corpus/P0/ga4gh-genetic-discrimination-position-statement.txt",
        extractor="pdf_text",
        must_contain=["Position Statement on Genetic Discrimination", "genetic non-discrimination"],
        min_words=2500,
        note="Official GA4GH position statement, published February 2026.",
    ),
    Target(
        key="ga4gh-frs",
        title="Framework for Responsible Sharing of Genomic and Health-Related Data",
        url=_drive("1x0rXxndUWQCdiBvOBndnNioyDoX_MJoU"),
        out="data/corpus/P0/ga4gh-frs-en.pdf",
        extractor="binary",
        must_contain=[
            "Foundational Principles and Core Elements",
            "share in scientific advancement and its benefits",
        ],
        min_words=2500,
        note="v3, September 2019. English of 16 language variants on ga4gh.org/framework/.",
    ),
    Target(
        key="ga4gh-consent-policy",
        title="GA4GH Consent Policy v2.0",
        url=_drive("13V1fewFW7M38ztiU5WyW4UDL_q-yrvBk"),
        out="data/corpus/P0/ga4gh-consent-policy.pdf",
        extractor="binary",
        must_contain=["Consent Best Practices", "open, communicative, and continuing relationship"],
        min_words=1400,
        note="POL 002 / v2.0, September 2019.",
    ),
    Target(
        key="ga4gh-errp",
        title="GA4GH Ethics Review Recognition Policy",
        url=_drive("11lt1_8AwVlSJI-nJGnNDmfxK_2xq2pS_"),
        out="data/corpus/P0/ga4gh-ethics-review-recognition-policy.pdf",
        extractor="binary",
        must_contain=[
            "Essential Elements of Ethics Review",
            "improving mutual recognition among RECs",
        ],
        min_words=1600,
        note="POL 004 / v2.0, 8 July 2020. v1.0 (2017) is superseded.",
    ),
    Target(
        key="ga4gh-dacres",
        title="GA4GH Data Access Committee Guiding Principles and Procedural Standards Policy",
        url=_drive("1gGmQUNnWNQGN7maR6TE0GcGvPFt5qWop"),
        out="data/corpus/P0/ga4gh-dacres-policy.pdf",
        extractor="binary",
        must_contain=[
            "guiding principles and provide procedural standards for DACs",
            "engender greater trust in the DAC",
        ],
        min_words=2800,
        note="POL 008 / v1.0, 27 October 2021. The DACReS Toolkit's policy component.",
    ),
    # Not a PDF on ga4gh.org, and deliberately not the one that site offers: the
    # /document/data-security-infrastructure-policy/ page still serves v1.1 from 2015,
    # nine years superseded. GA4GH maintains the current text in a Git repository, so that
    # is the authoritative source. The version string is asserted below to keep it that way.
    Target(
        key="ga4gh-dsip",
        title="GA4GH Data Security Infrastructure Policy v4.0",
        url="https://raw.githubusercontent.com/ga4gh/data-security/master/DSIP/DSIP_v4.0.md",
        out="data/corpus/P0/ga4gh-data-security-infrastructure-policy.txt",
        extractor="markdown",
        must_contain=[
            "VERSION 4.0, September 25, 2019",
            "Security Technology Building Blocks",
            "Authorization and Access Control",
        ],
        min_words=5000,
        note="Official ga4gh/data-security repository. The website's copy is v1.1 (2015).",
    ),
]

# Regional statutes on their publisher's own English text.
#
# Two corrections to the record this replaces. Singapore's default SSO view really was a
# table of contents, but the test used to prove it — zero occurrences of "shall not" — was
# never a valid test: the 2020 Revised Edition converted "shall" to "must" throughout, so
# the full statute has none either. The obligation assertions below use "must not". And
# SSO answers a missing document with HTTP 200 and an HTML "Page Not Found" body, so these
# are only safe as binary targets, where the %PDF magic bytes are checked first.
REGIONAL: List[Target] = [
    Target(
        key="sg-pdpa",
        title="Singapore — Personal Data Protection Act 2012 (official)",
        url="https://sso.agc.gov.sg/Act/PDPA2012?ViewType=Pdf",
        out="data/corpus/P2/SG/personal-data-protection-act-2012.pdf",
        extractor="binary",
        must_contain=[
            "An organisation must not",
            "collect, use or disclose personal data",
            "guilty of an offence",
        ],
        min_words=30000,
        note="AGC Legislation Division. English is the authentic language; tracks the "
        "in-force consolidation, so content changes as the Act is amended.",
    ),
    Target(
        key="sg-hbra",
        title="Singapore — Human Biomedical Research Act 2015 (official)",
        url="https://sso.agc.gov.sg/Act/HBRA2015?ViewType=Pdf",
        out="data/corpus/P2/SG/human-biomedical-research-act-2015.pdf",
        extractor="binary",
        must_contain=[
            "must not be a research subject",
            "institutional review board",
            "guilty of an offence",
        ],
        min_words=20000,
        note="AGC Legislation Division.",
    ),
    Target(
        key="sg-human-biomedical-research-regulations",
        title="Singapore — Human Biomedical Research Regulations 2017",
        url="https://sso.agc.gov.sg/SL/HBRA2015-RG1?ViewType=Pdf",
        out="data/corpus/P2/SG/human-biomedical-research-regulations-2017.pdf",
        extractor="binary",
        must_contain=[
            "Human Biomedical Research Regulations 2017",
            "institutional review board",
            "Policy on incidental findings",
        ],
        min_words=7000,
        note="AGC Legislation Division; subsidiary legislation implementing the HBRA.",
    ),
    Target(
        key="sg-restricted-human-biomedical-research-regulations",
        title="Singapore — Human Biomedical Research (Restricted Research) Regulations 2017",
        url="https://sso.agc.gov.sg/SL/HBRA2015-RG2?ViewType=Pdf",
        out=(
            "data/corpus/P2/SG/"
            "human-biomedical-research-restricted-research-regulations-2017.pdf"
        ),
        extractor="binary",
        must_contain=[
            "restricted research",
            "special requirements in consent-taking",
            "oocyte and embryo donors",
        ],
        min_words=2500,
        note="AGC Legislation Division; subsidiary legislation implementing the HBRA.",
    ),
    Target(
        key="sg-tissue-banking",
        title="Singapore — Human Biomedical Research (Tissue Banking) Regulations",
        url=(
            "https://sso.agc.gov.sg/SL-Rev/HBRA2015-RG3/Published/20250530"
            "?DocDate=20250530&ViewType=Pdf"
        ),
        out="data/corpus/P2/SG/human-biomedical-research-tissue-banking-regulations.pdf",
        extractor="binary",
        must_contain=[
            "tissue banking activity",
            "removed, supplied or exported",
            "Policy on incidental findings",
        ],
        min_words=5000,
        note="AGC Legislation Division, 2020 Revised Edition as amended in 2025.",
    ),
    Target(
        key="sg-hia",
        title="Singapore — Health Information Act 2026 (official, uncommenced)",
        url=(
            "https://sso.agc.gov.sg/Acts-Supp/1-2026/Published/20260212"
            "?DocDate=20260212&ViewType=Pdf"
        ),
        out="data/corpus/P2/SG/health-information-act-2026.pdf",
        extractor="binary",
        must_contain=[
            "accessible health information",
            "must not disclose accessible health",
            "guilty of an offence",
        ],
        min_words=35000,
        note="Act 1 of 2026, assented 3 Feb 2026, not yet commenced (MOH targets 2027). "
        "Gazette Acts Supplement — the consolidated /Act/HIA2026 page rejects ViewType=Pdf.",
    ),
    # Hong Kong e-Legislation cannot be fetched — every route, including the noscript
    # escape hatch, ends at a 7.5 KB JavaScript shell. The Privacy Commissioner publishes
    # the Ordinance itself, so the regulator's own copy is used instead.
    # Korea and mainland China have no official English statute text. What follows is the
    # best available English rendering, and the manifest marks every one of them
    # `content_type: translation` so a citation never claims to be the law itself.
    #
    # Korea: the earlier attempt failed on lawView.do, which is a frameset wrapper of about
    # 170 words. The iframe target below is server-rendered and complete.
    Target(
        key="kr-bioethics",
        title="South Korea — Bioethics and Safety Act (KLRI English translation)",
        url="https://elaw.klri.re.kr/eng_service/lawViewContent.do?hseq=68583&lang=ENG",
        out="data/corpus/P2/KR/bioethics-and-safety-act.txt",
        extractor="klri",
        must_contain=[
            "ensure bioethics and safety",
            "human subjects research",
            "Consent to Genetic Testing",
        ],
        min_words=14000,
        note="Act No. 20327 (2024). KLRI states its translations are 'neither official nor "
        "legally effective'. The 2025 version exists but its English record is an empty stub.",
    ),
    Target(
        key="kr-pipa",
        title="South Korea — Personal Information Protection Act (KLRI English translation)",
        url="https://elaw.klri.re.kr/eng_service/lawViewContent.do?hseq=71740&lang=ENG",
        out="data/corpus/P2/KR/personal-information-protection-act.txt",
        extractor="klri",
        must_contain=[
            "Cross-border transfer of personal information",
            "personal information controller",
        ],
        min_words=28000,
        note="Act No. 20897, current version. KLRI translation, not official text.",
    ),
    Target(
        key="kr-bioethics-enforcement-decree",
        title="South Korea — Enforcement Decree of the Bioethics and Safety Act",
        url="https://elaw.klri.re.kr/eng_service/lawViewContent.do?hseq=71872&lang=ENG",
        out="data/corpus/P2/KR/bioethics-and-safety-act-enforcement-decree-en.txt",
        extractor="klri",
        must_contain=[
            "Meetings of the National Bioethics Committee",
            "Human Material Bank",
            "genetic tests",
        ],
        min_words=3000,
        note="KLRI reference translation through Presidential Decree No. 35811 (2025).",
    ),
    Target(
        key="kr-pipa-enforcement-decree",
        title="South Korea — Enforcement Decree of the Personal Information Protection Act",
        url="https://elaw.klri.re.kr/eng_service/lawViewContent.do?hseq=69668&lang=ENG",
        out="data/corpus/P2/KR/personal-information-protection-act-enforcement-decree-en.txt",
        extractor="klri",
        must_contain=["Pseudonymized Information", "Measures to Ensure Safety"],
        min_words=31000,
        note="Latest complete KLRI reference translation available for reproducible fetch "
        "as of August 2026 (Presidential Decree No. 35343, effective March 2025).",
    ),
    Target(
        key="cn-hgr",
        title="China — Regulation on the Management of Human Genetic Resources",
        url=(
            "https://www.chinalawtranslate.com/en/"
            "p-r-c-regulation-on-the-management-of-human-genetic-resources/"
        ),
        out="data/corpus/P2/CN/human-genetic-resources-regulation.txt",
        must_contain=[
            "must not collect or preserve human genetic resources",
            "international cooperation in scientific research",
        ],
        min_words=4000,
        note="Third-party translation. The State Council's English site carries only a "
        "412-word news summary; no official English full text exists.",
    ),
    Target(
        key="cn-hgr-rules",
        title="China — Implementation Rules for the Human Genetic Resources Regulation",
        url=(
            "https://www.chinalawtranslate.com/en/"
            "Implementation-Rules-for-the-Regulations-on-the-Management-of-"
            "Human-Genetic-Resources/"
        ),
        out="data/corpus/P2/CN/human-genetic-resources-implementation-rules.txt",
        must_contain=["Chinese Unit", "provision abroad"],
        min_words=6000,
        note="MOST Order No. 21, published in Chinese only. Third-party translation. These "
        "are the operative approval and filing rules for cross-border genomic transfer.",
    ),
    Target(
        key="cn-pipl",
        title="China — Personal Information Protection Law",
        url=(
            "https://en.spp.gov.cn/2021-12/29/c_948419.htm|"
            "https://en.spp.gov.cn/2021-12/29/c_948419_2.htm|"
            "https://en.spp.gov.cn/2021-12/29/c_948419_3.htm"
        ),
        out="data/corpus/P2/CN/personal-information-protection-law.txt",
        must_contain=[
            "provide personal information for a party outside",
            "passing the security assessment organized",
        ],
        min_words=5500,
        note="Paginated across three pages; the first alone stops at Article 25 and looks "
        "complete. Supreme People's Procuratorate, crediting en.npc.gov.cn, which labels "
        "its English texts 'for reference only'.",
    ),
    Target(
        key="cn-dsl",
        title="China — Data Security Law",
        url="http://www.npc.gov.cn/englishnpc/c2759/c23934/202112/t20211209_385109.html",
        out="data/corpus/P2/CN/data-security-law.txt",
        must_contain=[
            "requests for data made by foreign judicial",
            "data processing activities and security supervision",
        ],
        min_words=3500,
        note="The NPC's own English site — the most official of the China set, still "
        "published 'for reference only'.",
    ),
    Target(
        key="cn-crossborder-2024",
        title="China — Provisions on Promoting and Regulating Cross-Border Data Flows",
        url="https://www.cac.gov.cn/2024-03/22/c_1712776611775634.htm",
        out="data/corpus/P2/CN/cross-border-data-flow-provisions-2024-zh.txt",
        must_contain=["促进和规范数据跨境流动规定", "重要数据", "个人信息出境标准合同"],
        # Chinese has no spaces between lexical words; the cleaned 14-article text has
        # only ~44 whitespace-delimited tokens despite being several thousand characters.
        min_words=40,
        strip_before="促进和规范数据跨境流动规定",
        strip_after="中央网络安全和信息化委员会办公室 中华人民共和国国家互联网信息办公室 © 版权所有",
        note="Official Chinese text published by the Cyberspace Administration of China, "
        "effective 22 March 2024. No official English full text is available.",
    ),
    Target(
        key="cn-network-data-regulations",
        title="China — Regulations on Network Data Security Management",
        url="https://www.cac.gov.cn/2024-09/30/c_1729384452307680.htm",
        out="data/corpus/P2/CN/network-data-security-management-regulations-2024-zh.txt",
        must_contain=["网络数据安全管理条例", "个人信息保护", "网络数据出境安全管理"],
        # Same tokenisation caveat as the cross-border provisions above. The complete
        # cleaned 64-article text has ~241 whitespace-delimited tokens.
        min_words=230,
        strip_before="网络数据安全管理条例",
        strip_after="中央网络安全和信息化委员会办公室 中华人民共和国国家互联网信息办公室 © 版权所有",
        note="Official Chinese text published by the Cyberspace Administration of China; "
        "effective 1 January 2025. No official English full text is available.",
    ),
    Target(
        key="cn-human-research-ethics-review-measures-2023",
        title="China — Measures for Ethical Review of Life Science and Medical Research Involving Humans",
        url="https://www.natcm.gov.cn/kejisi/zhengcewenjian/2023-02-28/29341.html",
        out="data/corpus/P2/CN/human-research-ethics-review-measures-2023-zh.txt",
        extractor="html",
        must_contain=[
            "涉及人的生命科学和医学研究伦理审查办法",
            "生物样本、信息数据",
            "知情同意",
        ],
        min_words=80,
        min_chars=7000,
        strip_before="涉及人的生命科学和医学研究伦理审查办法",
        note="Official Chinese text jointly issued by the NHC and three other authorities.",
    ),
    Target(
        key="cn-biosafety-law-2024",
        title="China — Biosecurity Law (2024 revision)",
        url=(
            "https://www.nhc.gov.cn/qjjys/rlyczygl/202503/"
            "c5373f14621e4011b6cbc932184086a2/files/1746832759166_62590.pdf"
        ),
        out="data/corpus/P2/CN/biosecurity-law-2024-zh.pdf",
        extractor="binary",
        must_contain=[
            "人类遗传资源与生物资源安全管理",
            "开展国际科学研究合作",
            "未经批准",
        ],
        min_words=100,
        min_chars=12000,
        note="Official current Chinese text published by the National Health Commission.",
    ),
    Target(
        key="cn-data-export-security-assessment-measures",
        title="China — Measures for Security Assessment of Data Exports",
        url="https://www.cac.gov.cn/2022-07/07/c_1658811536396503.htm",
        out="data/corpus/P2/CN/data-export-security-assessment-measures-2022-zh.txt",
        extractor="html",
        must_contain=["数据出境安全评估办法", "数据出境风险自评估", "境外接收方"],
        min_words=35,
        min_chars=3000,
        strip_before="数据出境安全评估办法",
        note="Official Chinese text published by the Cyberspace Administration of China.",
    ),
    Target(
        key="cn-personal-information-export-standard-contract-measures",
        title="China — Measures and Standard Contract for Export of Personal Information",
        url=(
            "https://www.cac.gov.cn/2023-02/24/c_1678884830036813.htm|"
            "https://www.cac.gov.cn/rootimages/uploadimg/1678884832607075/1678884832607075.pdf"
        ),
        out=(
            "data/corpus/P2/CN/"
            "personal-information-export-standard-contract-measures-2023-zh.txt"
        ),
        extractor="mixed",
        must_contain=[
            "个人信息出境标准合同办法",
            "个人信息保护影响评估",
            "境外接收方",
        ],
        min_words=250,
        min_chars=9000,
        note="Official CAC measures followed by the complete official standard-contract annex.",
    ),
    Target(
        key="hk-pdpo",
        title="Hong Kong — Personal Data (Privacy) Ordinance (Cap. 486)",
        url="https://www.pcpd.org.hk/english/files/pdpo.pdf",
        out="data/corpus/P2/HK/personal-data-privacy-ordinance-cap486.pdf",
        extractor="binary",
        must_contain=[
            "Prohibition against transfer of personal data",
            "substantially similar to, or serves the same purposes",
            "not yet in operation",
        ],
        min_words=30000,
        note="Published by the PCPD. Consolidated to 18 of 2012 / E.R. 1 of 2013, so it "
        "predates the 2021 anti-doxxing amendments; s.33 itself is unamended and still "
        "marked not yet in operation.",
    ),
    Target(
        key="hk-crossborder-guidance",
        title="Hong Kong — PCPD Guidance on Personal Data Protection in Cross-border Transfer",
        url="https://www.pcpd.org.hk/english/resources_centre/publications/files/GN_crossborder_e.pdf",
        out="data/corpus/P2/HK/pcpd-cross-border-transfer-guidance.pdf",
        extractor="binary",
        must_contain=[
            "Personal Data Protection in Cross-border",
            "transfer of personal data to places outside Hong Kong",
        ],
        min_words=7000,
        note="PCPD Guidance Note — the due-diligence half of the s.33 practical guidance.",
    ),
    Target(
        key="hk-model-clauses",
        title="Hong Kong — PCPD Recommended Model Contractual Clauses",
        url=(
            "https://www.pcpd.org.hk/english/resources_centre/publications/files/"
            "guidance_model_contractual_clauses.pdf"
        ),
        out="data/corpus/P2/HK/pcpd-model-contractual-clauses.pdf",
        extractor="binary",
        must_contain=[
            "Recommended Model Contractual Clauses",
            "equivalent protection to the degree provided",
        ],
        min_words=4500,
        note="PCPD Guidance Note — the model-clauses half of the s.33 practical guidance.",
    ),
    Target(
        key="hk-ehealth-code-of-practice",
        title="Hong Kong — Code of Practice for Using Electronic Health Record for Healthcare",
        url=(
            "https://www.ehealth.gov.hk/filemanager/content/pdf/en/hcp/"
            "ehealth-code-of-practice.pdf"
        ),
        out="data/corpus/P2/HK/ehealth-code-of-practice.pdf",
        extractor="binary",
        must_contain=[
            "Code of Practice for Using Electronic Health Record for Healthcare",
            "Sharing Consent",
            "need-to-know",
        ],
        min_words=9000,
        note="Current official code issued under section 52 of Cap. 625.",
    ),
    Target(
        key="jp-ethical-guidelines",
        title="Japan — Ethical Guidelines for Medical and Biological Research Involving "
        "Human Subjects",
        url="https://www.mhlw.go.jp/content/001457376.pdf",
        out="data/corpus/P2/JP/ethical-guidelines-medical-biological-research.pdf",
        extractor="binary",
        must_contain=[
            "shall not disclose information obtained",
            "ethical review committee",
            "informed consent",
        ],
        min_words=15000,
        note="MEXT/MHLW/METI joint guidelines, 23 Mar 2021 as amended 27 Mar 2023. This "
        "superseded the 2015 'Medical and Health Research' guidelines of the same family. "
        "Reference translation; the Japanese text is the one with legal effect.",
    ),
    Target(
        key="jp-appi",
        title="Japan — Act on the Protection of Personal Information (reference translation)",
        url=(
            "https://www.japaneselawtranslation.go.jp/ja/laws/download/4241/09/"
            "h15Aa000570305en14.0_r3A37.pdf"
        ),
        out="data/corpus/P2/JP/act-on-protection-of-personal-information.pdf",
        extractor="binary",
        must_contain=[
            "Pseudonymized Personal Information",
            "Provision to a Third Party in a Foreign Country",
            "Sensitive personal information",
        ],
        min_words=30000,
        note="Government reference translation of Act No. 57 of 2003 as amended through "
        "Act No. 37 of 2021. The Japanese text has legal effect.",
    ),
    Target(
        key="jp-medical-data-secondary-use-act",
        title="Japan — Act on Anonymized and Pseudonymized Medical Information for R&D",
        url="https://laws.e-gov.go.jp/api/1/lawdata/429AC0000000028",
        out="data/corpus/P2/JP/medical-data-secondary-use-act-ja.txt",
        extractor="egov_xml",
        must_contain=["仮名加工医療情報作成事業者", "医療情報取扱事業者", "研究開発"],
        min_words=100,
        min_chars=30000,
        note="Official current Japanese text from the e-Gov Laws API.",
    ),
    Target(
        key="jp-genomic-medicine-promotion-act",
        title="Japan — Act on Comprehensive and Systematic Promotion of Genomic Medicine",
        url="https://laws.e-gov.go.jp/api/1/lawdata/505AC1000000057",
        out="data/corpus/P2/JP/genomic-medicine-promotion-act-2023-ja.txt",
        extractor="egov_xml",
        must_contain=["ゲノム情報", "生命倫理", "不当な差別"],
        min_words=30,
        min_chars=3000,
        note="Official Japanese Act No. 57 of 2023 from the e-Gov Laws API.",
    ),
    Target(
        key="jp-ethical-guidelines-guidance-2024",
        title="Japan — Guidance for the Ethical Guidelines for Life Science and Medical Research",
        url="https://www.mhlw.go.jp/content/001237478.pdf",
        out="data/corpus/P2/JP/ethical-guidelines-guidance-2024-ja.pdf",
        extractor="binary",
        must_contain=["インフォームド・コンセント", "外国にある者", "将来の研究"],
        min_words=1000,
        min_chars=100000,
        note="Official Japanese guidance dated 1 April 2024, published by MHLW.",
    ),
]

# The Consent Toolkit is six separate publications, not one document. Each is kept
# separate so a provision key names the clause set it came from — the lesson the two
# Taiwan Acts taught. The sixth component, Model Consent Clauses for Rare Disease
# Research, is a BMC journal article rather than a GA4GH-formatted clause table
# (Nguyen et al. 2019); it carries an abstract and keyword header that would be indexed
# as if it were operative text, so it is left out.
CONSENT_TOOLKIT: List[Target] = [
    Target(
        key="consent-clinical",
        title="GA4GH Clinical Genomic Consent Clauses",
        url=_drive("188pBO9vIBVXmEsLhdVCdKMUNPtGB_3H-"),
        out="data/corpus/P1/ga4gh-consent-clauses-clinical.pdf",
        extractor="binary",
        must_contain=[
            "Clinical Genomic Consent Clauses: Context and Use",
            "mandates returning clinically actionable results",
        ],
        min_words=4000,
        note="D015 / v6.0, 23 June 2022.",
    ),
    Target(
        key="consent-research",
        title="GA4GH Consent Clauses for Genomic Research",
        url=_drive("10j6og59Vd575EDj9EpIXo08S6-Md5i1_"),
        out="data/corpus/P1/ga4gh-consent-clauses-research.pdf",
        extractor="binary",
        must_contain=["List of Consent Elements", "Your DNA Your Say"],
        min_words=6000,
        note="8 July 2020.",
    ),
    Target(
        key="consent-large-scale",
        title="GA4GH Consent Clauses for Large Scale Initiatives",
        url=_drive("1EqJ6FbxVlYXhUX8M7THNQLmcwFnBUvMb"),
        out="data/corpus/P1/ga4gh-consent-clauses-large-scale.pdf",
        extractor="binary",
        must_contain=["personal genome biobanks", "biobanking and population studies"],
        min_words=4000,
        note="D014 / v1.0, 21 April 2022.",
    ),
    Target(
        key="consent-familial",
        title="GA4GH Familial Consent Clauses",
        url=_drive("1csYxGI2zNXuNEm4TDJspSoU3RA0duLXa"),
        out="data/corpus/P1/ga4gh-consent-clauses-familial.pdf",
        extractor="binary",
        must_contain=["A Legal Duty to Communicate", "public health interventionist approach"],
        min_words=900,
        note="D011 / v1.0, 20 January 2021.",
    ),
    Target(
        key="consent-pediatric",
        title="GA4GH Pediatric Consent to Genetic Research: Clauses",
        url=_drive("19dgh_0VWUqHbdHvmE_Y_ugXjxumDH_zQ"),
        out="data/corpus/P1/ga4gh-consent-clauses-pediatric.pdf",
        extractor="binary",
        must_contain=["mature minor rule", "varying levels of maturity"],
        min_words=1300,
        note="D012a / v1.0, 27 October 2021.",
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

ALL_TARGETS: List[Target] = TARGETS + CONSENT_TOOLKIT + REGIONAL + GA4GH_PAGES


def _get(
    url: str,
    accept: Optional[Dict[str, str]] = None,
    timeout: int = 120,
    attempts: int = 3,
) -> bytes:
    """
    Fetch a URL, retrying transient network failures.

    Publishers drop connections mid-body — ga4gh.org's TLS and Google Drive both do it,
    and a truncated read raises IncompleteRead partway through a multi-hundred-KB PDF.
    Without a retry the whole run dies on one flaky target, which for a tool whose job is
    rebuilding the corpus is a failure mode worse than the flake itself.
    """
    # Some publishers reject a request carrying only a User-Agent as non-browser traffic:
    # chinalawtranslate.com answers 403 without these two and 200 with them. Anything an
    # extractor passes explicitly still wins — the CELLAR fetch negotiates its own Accept.
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if accept:
        headers.update(accept)
    request = urllib.request.Request(url, headers=headers)
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 — one more try beats aborting the sweep
            last = exc
            if attempt < attempts:
                time.sleep(POLITE_DELAY_S * attempt)
    raise RuntimeError(f"{type(last).__name__} after {attempts} attempts: {last}") from last


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
        if not re.match(r"^L_\d+[A-Z]{2}\.\d+(?:\.fmx)?\.xml\b", ln)
        and not re.match(r"^Official Journal of the European Union\s*L?\s*[\d/]*$", ln)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_cellar(t: Target) -> str:
    raw = _decode(
        _get(t.url, {"Accept": "application/xhtml+xml", "Accept-Language": "eng"}, timeout=180)
    )
    return _clean_xhtml(raw)


def _extract_html_page(url: str, seen: set) -> tuple:
    root = LH.fromstring(_decode(_get(url)))
    for bad in root.xpath("//script|//style|//nav|//header|//footer|//form|//noscript"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    node = root.xpath("//main") or root.xpath("//article") or [root]
    blocks = []
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
    return blocks, seen


def extract_html(t: Target) -> str:
    """
    Text of one or more HTML pages, joined.

    A ``|``-separated url fetches several pages into one document, because some publishers
    paginate a single statute — China's PIPL is served in three parts, and fetching only
    the first yields Articles 1-25 and looks complete. Deduplication is shared across the
    pages so site chrome repeated on each one is emitted at most once.
    """
    blocks: List[str] = []
    seen: set = set()
    for url in t.url.split("|"):
        page_blocks, seen = _extract_html_page(url, seen)
        blocks.extend(page_blocks)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(blocks)).strip()


def extract_mixed(t: Target) -> str:
    """Join official HTML and PDF parts of one instrument into an auditable text file."""
    parts: List[str] = []
    for url in t.url.split("|"):
        raw = _get(url, timeout=180)
        if raw.startswith(b"%PDF"):
            parts.append(_pdf_text(raw))
        else:
            root = LH.fromstring(raw)
            for bad in root.xpath("//script|//style|//nav|//header|//footer|//form|//noscript"):
                parent = bad.getparent()
                if parent is not None:
                    parent.remove(bad)
            node = root.xpath("//main") or root.xpath("//article") or [root]
            text = node[0].text_content()
            lines = [" ".join(line.split()) for line in text.splitlines()]
            parts.append("\n".join(line for line in lines if line))
        time.sleep(POLITE_DELAY_S)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()


def extract_egov_xml(t: Target) -> str:
    """Extract the official Japanese law title and each article from the e-Gov XML API."""
    root = LET.fromstring(_get(t.url))
    blocks: List[str] = []
    titles = root.xpath("//*[local-name()='LawTitle']")
    if titles:
        blocks.append(" ".join(titles[0].itertext()).strip())
    for article in root.xpath("//*[local-name()='Article']"):
        headings = article.xpath("./*[local-name()='ArticleTitle']")
        heading = " ".join(headings[0].itertext()).strip() if headings else ""
        sentences = [
            " ".join(node.itertext()).strip()
            for node in article.xpath(".//*[local-name()='Sentence']")
        ]
        body = " ".join(sentence for sentence in sentences if sentence)
        if heading and body:
            blocks.append(f"\n{heading}\n\n{body}")
    if len(blocks) < 5:
        raise RuntimeError(f"only {len(blocks) - 1} articles parsed from {t.url}")
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(blocks)).strip()


#: Screen-reader caption on every KLRI block table — "law view screen", not content.
KLRI_CAPTION = "법령보기 화면"


def extract_klri(t: Target) -> str:
    """
    Extract a Korean statute from KLRI's table-per-block layout.

    Each block is its own ``<table>``: those captioned 법령보기 화면 carry an article
    designation, the uncaptioned ones carry its paragraphs. Nothing is in a ``<p>``, which
    is why the generic HTML extractor returned 74 words from a 16,000-word Act — a failure
    the validation floor caught rather than indexing.
    """
    root = LH.fromstring(_decode(_get(t.url)))
    for bad in root.xpath("//script|//style"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    blocks: List[str] = []
    for table in root.xpath("//table"):
        if table.xpath(".//table"):  # outer wrapper; its rows are visited on their own
            continue
        for cap in table.xpath("./caption"):
            cap.drop_tree()
        text = " ".join(table.text_content().split()).replace(KLRI_CAPTION, "").strip()
        # "-->" survives as an orphaned comment closer in this markup.
        if not text or text == "-->":
            continue
        if re.match(r"^Article\s+\d", text):
            blocks.append("\n" + text + "\n")  # blank-line delimited -> detect_headings
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


def extract_markdown(t: Target) -> str:
    """
    Flatten Markdown into the blank-line-delimited shape the chunker expects.

    GA4GH publishes the current Data Security Infrastructure Policy as Markdown in a Git
    repository, not as a PDF on the website — see the DSIP target for why that matters.
    The source is hard-wrapped near column 75, so paragraphs are rejoined; left wrapped,
    every provision would be split mid-sentence and no heading would survive detection.
    """
    raw = _decode(_get(t.url))
    blocks: List[str] = []
    para: List[str] = []

    def flush() -> None:
        if para:
            blocks.append(" ".join(para))
            para.clear()

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("#"):
            flush()
            # Blank-line delimited, so ingestion's detect_headings sees a section.
            blocks.append("\n" + stripped.lstrip("#").strip() + "\n")
        elif stripped.startswith(("- ", "* ", "|", ">")) or re.match(r"^\d+\.\s", stripped):
            flush()
            blocks.append(stripped)
        else:
            para.append(stripped)
    flush()
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(blocks)).strip()


def extract_pdf_text(t: Target) -> str:
    """Download a PDF and persist its extracted text for auditable text-based ingest."""
    data = _get(t.url, timeout=180)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({len(data)} bytes)")
    text = _pdf_text(data)
    # GA4GH PDFs place a page number directly before the running header (and, for the
    # Lexicon, before the first word of each page). These exact publisher patterns were
    # audited against the fetched files; removing them prevents a header from splitting an
    # otherwise contiguous model clause.
    text = re.sub(
        r"(?m)^\d{1,2}\s*(?:Global Alliance for Genomics and Health|"
        r"GA4GH Data Privacy and Security Policy)\s*$",
        "",
        text,
    )
    if t.key == "ga4gh-data-sharing-lexicon":
        text = re.sub(r"(?m)^(?:[1-9]|10)(?=[A-Z][a-z])", "", text)
    return text


def extract_pdf_text_cli(t: Target) -> str:
    """Extract a PDF whose embedded SymbolSet font is unsupported by pypdf.

    This is deliberately limited to fetch-time corpus rebuilding. The persisted artifact
    is plain text, so normal installs and ``--check`` do not require Poppler.
    """
    command = shutil.which("pdftotext")
    if command is None:
        raise RuntimeError("pdftotext is required to rebuild this source (install Poppler)")
    data = _get(t.url, timeout=180)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({len(data)} bytes)")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
        source.write(data)
        source.flush()
        result = subprocess.run(
            [command, "-layout", source.name, "-"],
            check=True,
            capture_output=True,
            timeout=180,
        )
    return result.stdout.decode("utf-8", errors="replace")


EXTRACTORS: Dict[str, Callable[[Target], str]] = {
    "cellar": extract_cellar,
    "html": extract_html,
    "mixed": extract_mixed,
    "egov_xml": extract_egov_xml,
    "klri": extract_klri,
    "markdown": extract_markdown,
    "moj_tw": extract_moj_tw,
    "pdf_text": extract_pdf_text,
    "pdf_text_cli": extract_pdf_text_cli,
}


def _pdf_text(data: bytes) -> str:
    """Text of a PDF held in memory, for validating a binary fetch before writing it."""
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


#: Characters that break a literal phrase match without being visible in the rendered
#: document. GA4GH's PDFs carry soft hyphens and zero-width spaces mid-word, and typeset
#: curly quotes where the phrase was copied with straight ones.
_INVISIBLE = str.maketrans({"­": "", "​": "", "’": "'", "‘": "'", "“": '"', "”": '"'})


def _normalise(text: str) -> str:
    """
    Reduce text to comparable letters: drop invisible characters and all whitespace.

    Whitespace is removed entirely, not merely collapsed, because PDF extraction puts it in
    the wrong places in both directions. Singapore's statutes come out of pypdf as "guilty
    of an of fence" and "THE ST A TUTES"; GA4GH's policies glue words together and insert
    soft hyphens mid-word; the DSIP Markdown is hard-wrapped near column 75. An assertion
    is about whether the document says a thing, and none of that changes the answer.
    """
    return "".join(text.translate(_INVISIBLE).split())


def validate(t: Target, text: str) -> List[str]:
    """Reasons this content must not be written. Empty list means it passed."""
    problems = []
    words = len(text.split())
    if words < t.min_words:
        problems.append(f"only {words} words, expected >= {t.min_words}")
    characters = len("".join(text.split()))
    if characters < t.min_chars:
        problems.append(f"only {characters} characters, expected >= {t.min_chars}")
    lowered = _normalise(text).lower()
    for phrase in t.must_contain:
        if _normalise(phrase).lower() not in lowered:
            problems.append(
                f"missing required phrase {phrase!r} — likely a table of contents, "
                "a cover page, or the wrong document"
            )
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
        # A PDF used to be accepted on its magic bytes alone, so must_contain and
        # min_words were dead settings on every binary target: a cover sheet, an
        # error page saved as PDF, or the wrong document would all have been written.
        # Validate the extracted text, exactly as the HTML path does.
        try:
            text = _pdf_text(data)
        except Exception as exc:  # noqa: BLE001 — an unreadable PDF is a failed fetch
            print(f"  REJECT {t.key}: PDF text extraction failed: {str(exc)[:80]}")
            return False
        problems = validate(t, text)
        if problems:
            print(f"  REJECT {t.key}: {'; '.join(problems)}")
            print("         nothing written — check the link still points at the document")
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

    if t.strip_before:
        cut = body.find(t.strip_before)
        if cut < 0:
            print(f"  REJECT {t.key}: strip_before marker {t.strip_before!r} not found")
            return False
        body = body[cut:]

    if t.strip_after:
        cut = body.find(t.strip_after)
        if cut < 0:
            print(f"  REJECT {t.key}: strip_after marker {t.strip_after!r} not found")
            return False
        body = body[:cut].rstrip()

    problems = validate(t, body)
    if problems:
        print(f"  REJECT {t.key}: {'; '.join(problems)}")
        print("         nothing written — a table of contents pollutes retrieval")
        return False

    # Provenance goes at the end: as a leading block it became its own chunk, an
    # indexable citation consisting of a URL. The manifest remains the authoritative record.
    footer = f"\n\n---\nSource: {t.url.split('|')[0]}\nRetrieved: {RETRIEVED}\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"{t.title}\n\n{body}{footer}", encoding="utf-8")
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
            try:
                problems = validate(t, _pdf_text(path.read_bytes()))
            except Exception as exc:  # noqa: BLE001 — report, do not abort the sweep
                print(f"  BAD     {t.key}: unreadable PDF: {str(exc)[:80]}")
                failures += 1
                continue
            if problems:
                print(f"  BAD     {t.key}: {'; '.join(problems)}")
                failures += 1
            else:
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
