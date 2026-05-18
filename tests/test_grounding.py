import unittest

from src.regbot.grounding import (
    allowed_chunk_ids,
    audit_citation_grounding,
    audit_report_grounding,
    normalize_recommendations,
)


class TestGrounding(unittest.TestCase):
    def test_allowed_ids(self) -> None:
        chunks = [{"id": "a1"}, {"id": "b2"}]
        self.assertEqual(allowed_chunk_ids(chunks), {"a1", "b2"})

    def test_normalize_legacy_strings(self) -> None:
        raw = ["a", {"text": "b", "evidence_chunk_ids": ["x"]}]
        out = normalize_recommendations(raw)
        self.assertEqual(out[0]["text"], "a")
        self.assertEqual(out[0]["evidence_chunk_ids"], [])
        self.assertEqual(out[1]["evidence_chunk_ids"], ["x"])

    def test_audit_rejects_invalid_evidence_id(self) -> None:
        allow = {"c1", "c2"}
        report = {
            "recommendations": [
                {"text": "do something", "evidence_chunk_ids": ["nope"]},
            ],
        }
        audit = audit_report_grounding(report, allow)
        self.assertFalse(audit["ok"])
        self.assertTrue(any("Invalid evidence_chunk_ids" in i for i in audit["issues"]))

    def test_audit_requires_evidence_per_rec(self) -> None:
        allow = {"c1"}
        report = {
            "recommendations": [
                {"text": "r1", "evidence_chunk_ids": ["c1"]},
                {"text": "r2", "evidence_chunk_ids": []},
            ],
        }
        audit = audit_report_grounding(report, allow)
        self.assertFalse(audit["ok"])
        self.assertTrue(any("empty evidence_chunk_ids" in i for i in audit["issues"]))

    def test_audit_ok_structured(self) -> None:
        allow = {"c1", "c2"}
        report = {
            "recommendations": [
                {"text": "one", "evidence_chunk_ids": ["c1"]},
                {"text": "two", "evidence_chunk_ids": ["c2", "c1"]},
            ],
        }
        audit = audit_report_grounding(report, allow)
        self.assertTrue(audit["ok"])

    def test_legacy_wrapper_includes_citation_counts(self) -> None:
        allow = {"c1"}
        report = {
            "recommendations": [{"text": "t", "evidence_chunk_ids": ["c1"]}],
            "citations": [{"chunk_id": "c1", "reason": "x"}],
        }
        audit = audit_citation_grounding(
            report, allow, strict_min_citations_vs_recommendations=True
        )
        self.assertTrue(audit["ok"])
        self.assertEqual(audit.get("citation_count"), 1)


if __name__ == "__main__":
    unittest.main()
