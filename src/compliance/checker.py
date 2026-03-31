from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
from pypdf import PdfReader
import os

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


def extract_text(file_path_or_bytes, filename: str = "") -> str:
    """
    Extract raw text from a consent form.

    Accepts either a file path string (CLI usage) or a BytesIO object
    (Streamlit usage). For PDFs, uses PyPDFLoader for file paths and
    PdfReader for BytesIO objects. For TXT, reads directly from path
    or decodes bytes.

    Args:
        file_path_or_bytes: File path string or BytesIO object.
        filename: Original filename, used to detect file type
                  when a BytesIO object is passed.

    Returns:
        Full text content of the consent form as a single string.

    Raises:
        ValueError: If the file type cannot be determined or is unsupported.
    """
    if isinstance(file_path_or_bytes, str):
        file_path = file_path_or_bytes
        if file_path.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
            pages  = loader.load()
            return " ".join([page.page_content for page in pages])
        if file_path.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        raise ValueError(f"Unsupported file type: {file_path}. Only PDF and TXT are supported.")

    else:
        name = filename.lower()
        if name.endswith(".pdf"):
            reader = PdfReader(file_path_or_bytes)
            return " ".join([page.extract_text() or "" for page in reader.pages])
        if name.endswith(".txt"):
            return file_path_or_bytes.read().decode("utf-8")
        raise ValueError(f"Unsupported file type: {filename}. Only PDF and TXT are supported.")


def detect_study_type(consent_text: str) -> list:
    """
    Detect study types present in the consent form text.

    Scans the consent form against STUDY_TYPE_KEYWORDS from config.py using
    case-insensitive keyword matching. A study type is detected if any of its
    keywords appear in the text. Multiple study types can be detected from a
    single form.

    Args:
        consent_text: Full text content of the consent form.

    Returns:
        List of detected study type strings (e.g. ['pediatric', 'familial']).
        Returns an empty list if no study type keywords are matched.
    """
    text = consent_text.lower()
    detected_types = []
    for study_type, keywords in STUDY_TYPE_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            detected_types.append(study_type)
    return detected_types


def build_check_queue(detected_types: list) -> list:
    """
    Build the full list of compliance checks to run for this consent form.

    Always starts with the eight universal checks from UNIVERSAL_MANDATORY_CHECKS,
    then appends conditional checks from CONDITIONAL_MANDATORY_CHECKS for each
    detected study type. The final queue can contain up to 21 checks for a form
    covering all five study types.

    Args:
        detected_types: List of study types from detect_study_type().

    Returns:
        Ordered list of check name strings to run.
    """
    checks = list(UNIVERSAL_MANDATORY_CHECKS)
    for study_type in detected_types:
        checks.extend(CONDITIONAL_MANDATORY_CHECKS.get(study_type, []))
    return checks


def _format_chunks(check_name: str, chunks: list) -> str:
    """
    Format retrieved chunks with citations for a single compliance check.

    Produces a block starting with the check name followed by each retrieved
    chunk prefixed with its source citation. Citation includes document name,
    section if available, and page number.

    Args:
        check_name: Name of the compliance check (e.g. 'withdrawal_rights').
        chunks:     List of retrieved Document objects with metadata.

    Returns:
        Formatted string block ready for injection into the LLM prompt.
    """
    lines = [f"CHECK: {check_name}"]
    for doc in chunks:
        source = doc.metadata.get("source", "Unknown")
        section = doc.metadata.get("section", "")
        page = doc.metadata.get("page", "")
        citation = f"[{source}"
        if section:
            citation += f", {section}"
        if page:
            citation += f", page {page}"
        citation += "]"
        lines.append(f"{citation}\n{doc.page_content.strip()}")
    return "\n\n".join(lines)


def _parse_response(response_text: str) -> list:
    """
    Parse the LLM response into a list of structured verdict dicts.

    Expects the LLM to return one block per check using CHECK as the block
    separator. Parses each block line by line extracting check name, verdict,
    reason, and citation. Blocks with no content are skipped.

    Args:
        response_text: Raw string response from the LLM.

    Returns:
        List of dicts, each with keys: check, verdict, reason, citation.
    """
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


def run_compliance_check(consent_text: str, retriever, llm=None) -> list:
    """
    Run the full compliance check pipeline on an uploaded consent form.

    Accepts pre-extracted consent form text, detects study types, builds the check queue,
    retrieves relevant GA4GH chunks for each check, and passes everything to
    the LLM in a single call. The single LLM call design sends the consent form
    once regardless of check count, minimizing token usage.

    Args:
        file_path: Path to the uploaded consent form (PDF or TXT).
        retriever: EnsembleRetriever instance from load_retriever().
        llm:       ChatOpenAI instance for compliance verdict generation.

    Returns:
        List of verdict dicts, each with keys: check, verdict, reason, citation.
    """

    detected_types = detect_study_type(consent_text)
    check_queue    = build_check_queue(detected_types)

    print(f"Detected study types: {detected_types}")
    print(f"Running {len(check_queue)} compliance checks...")

    all_checks_formatted = []
    for check in check_queue:
        query = CHECK_QUERIES[check]
        subcategory = CHECK_SUBCATEGORY.get(check, None)
        chunks = retrieve(retriever, query, subcategory=subcategory)
        all_checks_formatted.append(_format_chunks(check, chunks))

    all_checks_with_chunks = "\n\n" + "="*60 + "\n\n".join(all_checks_formatted)
    prompt = COMPLIANCE_CHECK_PROMPT.format(
        all_checks_with_chunks=all_checks_with_chunks,
        consent_form_text=consent_text,
    )

    backend = os.environ.get("LLM_BACKEND", "openai")

    if backend == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        response = model.generate_content(prompt)
        return _parse_response(response.text)
    else:
        response = llm.invoke(prompt)
        return _parse_response(response.content)