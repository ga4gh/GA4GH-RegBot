# tests/test_checker.py — GA4GH RegBot
# Tests for compliance checker pipeline
# Run: pytest tests/test_checker.py -v

from src.compliance.checker import extract_text, detect_study_type, build_check_queue, _parse_response
from config import UNIVERSAL_MANDATORY_CHECKS


# extract_text

def test_extract_text_txt(tmp_path):
    f = tmp_path / "consent.txt"
    f.write_text("This is a test consent form.")
    result = extract_text(str(f))
    assert "test consent form" in result


# detect_study_type

def test_detects_pediatric():
    text = "This study involves children and requires parental consent and minor assent."
    result = detect_study_type(text)
    assert "pediatric" in result


def test_detects_familial():
    text = "This study involves family members and relatives sharing genetic data."
    result = detect_study_type(text)
    assert "familial" in result


def test_detects_no_type():
    text = "This is a general genomic research consent form."
    result = detect_study_type(text)
    assert result == []


def test_detects_multiple_types():
    text = "This study involves children with rare disease and family members."
    result = detect_study_type(text)
    assert "pediatric" in result
    assert "rare_disease" in result


# build_check_queue

def test_universal_checks_always_included():
    queue = build_check_queue([])
    for check in UNIVERSAL_MANDATORY_CHECKS:
        assert check in queue


def test_conditional_checks_added_for_pediatric():
    queue = build_check_queue(["pediatric"])
    assert "minor_assent_process" in queue
    assert "recontact_at_majority" in queue


#  _parse_response

def test_parse_response_single_verdict():
    response = """CHECK: withdrawal_rights
VERDICT: NON-COMPLIANT
REASON: No opt-out clause found in consent form.
CITATION: GA4GH Consent Policy POL 002, Section II Transparency"""
    result = _parse_response(response)
    assert len(result) == 1
    assert result[0]["verdict"] == "NON-COMPLIANT"
    assert result[0]["check"] == "withdrawal_rights"
    assert result[0]["citation"] == "GA4GH Consent Policy POL 002, Section II Transparency"


def test_parse_response_multiple_verdicts():
    response = """CHECK: withdrawal_rights
VERDICT: NON-COMPLIANT
REASON: No opt-out clause found.
CITATION: GA4GH Consent Policy POL 002, Section II

---

CHECK: data_sharing_purpose
VERDICT: COMPLIANT
REASON: Form clearly states research purpose.
CITATION: GA4GH Framework for Responsible Sharing, Section I"""
    result = _parse_response(response)
    assert len(result) == 2
    assert result[0]["check"] == "withdrawal_rights"
    assert result[1]["check"] == "data_sharing_purpose"