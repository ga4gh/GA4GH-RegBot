from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI

from config import (
    CHECK_QUERIES,
    STUDY_TYPE_KEYWORDS,
    UNIVERSAL_MANDATORY_CHECKS,
    CONDITIONAL_MANDATORY_CHECKS,
)
from src.retrieval.retriever import retrieve
from src.compliance.prompts import COMPLIANCE_CHECK_PROMPT


# Subcategory filter per conditional check for scoped retrieval
CHECK_SUBCATEGORY = {
    "minor_assent_process":          "pediatric",
    "recontact_at_majority":         "pediatric",
    "family_disclosure_approach":    "familial",
    "stigmatization_warning":        "familial",
    "data_linkage_matchmaking":      "rare_disease",
    "family_enrollment_policy":      "rare_disease",
    "secondary_research_use":        "large_scale",
    "biobank_storage_duration":      "large_scale",
    "results_reporting_policy":      "clinical_genomic",
    "genomic_testing_limitations":   "clinical_genomic",
    "recontact_policy":              "clinical_genomic",
    "genetic_discrimination_risk":   "clinical_genomic",
    "dna_data_destruction_policy":   "clinical_genomic",
}


def extract_text(file_path: str) -> str:
    """Extract raw text from uploaded consent form — PDF or txt."""
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
        pages  = loader.load()
        return " ".join([page.page_content for page in pages])
    if file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    raise ValueError(f"Unsupported file type: {file_path}. Only PDF and TXT are supported.")

def detect_study_type(consent_text: str) -> list:
    """Return list of study types detected from consent form text."""
    text           = consent_text.lower()
    detected_types = []
    for study_type, keywords in STUDY_TYPE_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            detected_types.append(study_type)
    return detected_types


def build_check_queue(detected_types: list) -> list:
    """Return full list of checks — universal + conditional per detected type."""
    checks = list(UNIVERSAL_MANDATORY_CHECKS)
    for study_type in detected_types:
        checks.extend(CONDITIONAL_MANDATORY_CHECKS.get(study_type, []))
    return checks


def _format_chunks(check_name: str, chunks: list) -> str:
    """Format retrieved chunks with source citations for one check."""
    lines = [f"CHECK: {check_name}"]
    for doc in chunks:
        source   = doc.metadata.get("source", "Unknown")
        section  = doc.metadata.get("section", "")
        page     = doc.metadata.get("page", "")
        citation = f"[{source}"
        if section:
            citation += f", {section}"
        if page:
            citation += f", page {page}"
        citation += "]"
        lines.append(f"{citation}\n{doc.page_content.strip()}")
    return "\n\n".join(lines)


def _parse_response(response_text: str) -> list:
    """Parse LLM response into list of verdict dicts."""
    verdicts = []
    lines    = response_text.strip().splitlines()
    verdict  = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("CHECK:"):
            if verdict:
                verdicts.append(verdict)
            verdict = {"check": line.replace("CHECK:", "").strip()}
        elif line.startswith("VERDICT:"):
            verdict["verdict"]  = line.replace("VERDICT:", "").strip()
        elif line.startswith("REASON:"):
            verdict["reason"]   = line.replace("REASON:", "").strip()
        elif line.startswith("CITATION:"):
            verdict["citation"] = line.replace("CITATION:", "").strip()

    if verdict:
        verdicts.append(verdict)

    return verdicts


def run_compliance_check(file_path: str, retriever, llm: ChatOpenAI) -> list:
    """
    Full compliance check pipeline. Returns list of verdict dicts.
    Each dict has: check, verdict, reason, citation.
    """
    consent_text   = extract_text(file_path)
    detected_types = detect_study_type(consent_text)
    check_queue    = build_check_queue(detected_types)

    print(f"Detected study types: {detected_types}")
    print(f"Running {len(check_queue)} compliance checks...")

    all_checks_formatted = []
    for check in check_queue:
        query       = CHECK_QUERIES[check]
        subcategory = CHECK_SUBCATEGORY.get(check, None)
        chunks      = retrieve(retriever, query, subcategory=subcategory)
        all_checks_formatted.append(_format_chunks(check, chunks))

    all_checks_with_chunks = "\n\n" + "="*60 + "\n\n".join(all_checks_formatted)
    prompt = COMPLIANCE_CHECK_PROMPT.format(
        all_checks_with_chunks=all_checks_with_chunks,
        consent_form_text=consent_text,
    )

    response = llm.invoke(prompt)
    return _parse_response(response.content)