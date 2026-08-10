import unittest
from typing import Any, Dict, List

from src.regbot.compliance import analyze_compliance
from src.regbot.evidence import (
    apply_phase3_enrichment,
    assess_human_review,
    build_evidence,
    describe_relevance,
    enrich_recommendations,
    governance_hint,
    select_quote,
    shared_terms,
)

CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "sg_p0_c1",
        "text": (
            "Consent must be informed and voluntary. Transfer limitation obligation: "
            "organisations must not transfer personal data outside Singapore unless the "
            "receiving country ensures a comparable standard of protection. "
            "Protection obligation and retention: reasonable security arrangements."
        ),
        "metadata": {
            "source": "pdpa-hbra-excerpt.txt",
            "page": 0,
            "document_id": "sg-law-excerpt",
            "jurisdiction": "SG",
            "framework": "national",
        },
    },
    {
        "id": "eu_p0_c0",
        "text": (
            "Article 35 of the GDPR requires data controllers to perform a Data Protection "
            "Impact Assessment before processing likely to result in a high risk."
        ),
        "metadata": {
            "source": "gdpr-dpia-genomic-research.txt",
            "page": 0,
            "document_id": "gdpr-dpia-genomic-research",
            "jurisdiction": "EU",
            "framework": "GDPR",
        },
    },
]


class TestQuoteSelection(unittest.TestCase):
    def test_quote_is_verbatim_from_chunk(self) -> None:
        rec = "State whether data may be transferred outside Singapore."
        quote = select_quote(rec, CHUNKS[0]["text"])
        self.assertIn(quote.rstrip("…").strip(), " ".join(CHUNKS[0]["text"].split()))

    def test_quote_targets_the_relevant_span(self) -> None:
        rec = "Clarify transfer of personal data outside Singapore."
        self.assertIn("outside Singapore", select_quote(rec, CHUNKS[0]["text"]))

    def test_quote_prefers_matching_span_over_first_sentence(self) -> None:
        rec = "Describe security arrangements and retention."
        quote = select_quote(rec, CHUNKS[0]["text"])
        self.assertIn("security", quote.lower())

    def test_quote_falls_back_when_nothing_overlaps(self) -> None:
        quote = select_quote("zzzz qqqq", CHUNKS[1]["text"])
        self.assertTrue(quote)

    def test_quote_is_truncated_with_ellipsis(self) -> None:
        long_chunk = "word " * 400
        quote = select_quote("word", long_chunk, max_chars=50)
        self.assertLessEqual(len(quote), 50)
        self.assertTrue(quote.endswith("…"))

    def test_empty_chunk_gives_empty_quote(self) -> None:
        self.assertEqual(select_quote("anything", ""), "")


class TestRelevance(unittest.TestCase):
    def test_shared_terms_exclude_stopwords_and_short_tokens(self) -> None:
        terms = shared_terms("The data must be transferred with consent", CHUNKS[0]["text"])
        self.assertNotIn("the", terms)
        self.assertNotIn("data", terms)  # too common in policy prose
        self.assertIn("consent", terms)

    def test_relevance_states_the_lexical_link(self) -> None:
        text = describe_relevance("transfer personal data outside Singapore", CHUNKS[0]["text"])
        self.assertIn("Shares terminology", text)
        self.assertIn("singapore", text.lower())

    def test_relevance_is_explicit_when_no_overlap(self) -> None:
        text = describe_relevance("zzzz qqqq", CHUNKS[1]["text"])
        self.assertIn("verify manually", text)


class TestGovernanceHint(unittest.TestCase):
    def test_jurisdiction_hint(self) -> None:
        self.assertIn("HBRA", str(governance_hint({"jurisdiction": "SG"})))
        self.assertIn("Data Protection Officer", str(governance_hint({"jurisdiction": "EU"})))
        self.assertIn("Data Access Committee", str(governance_hint({"jurisdiction": "GA4GH"})))

    def test_framework_fallback_when_jurisdiction_unknown(self) -> None:
        self.assertIn("Data Protection Officer", str(governance_hint({"framework": "GDPR"})))

    def test_no_hint_without_metadata(self) -> None:
        self.assertIsNone(governance_hint(None))
        self.assertIsNone(governance_hint({"source": "x.pdf"}))


class TestBuildEvidence(unittest.TestCase):
    def test_evidence_carries_review_fields(self) -> None:
        ev = build_evidence("transfer outside Singapore", ["sg_p0_c1"], CHUNKS)
        self.assertEqual(len(ev), 1)
        entry = ev[0]
        self.assertTrue(entry["resolved"])
        self.assertEqual(entry["chunk_id"], "sg_p0_c1")
        self.assertEqual(entry["source"], "pdpa-hbra-excerpt.txt")
        self.assertEqual(entry["page"], 0)
        self.assertEqual(entry["document_id"], "sg-law-excerpt")
        self.assertEqual(entry["jurisdiction"], "SG")
        self.assertTrue(entry["quote"])
        self.assertTrue(entry["relevance"])
        self.assertIn("HBRA", entry["governance_hint"])

    def test_unresolved_id_is_marked_not_dropped(self) -> None:
        ev = build_evidence("anything", ["ghost_id"], CHUNKS)
        self.assertEqual(ev[0]["chunk_id"], "ghost_id")
        self.assertFalse(ev[0]["resolved"])
        self.assertNotIn("quote", ev[0])

    def test_enrich_preserves_existing_recommendation_keys(self) -> None:
        recs = [
            {
                "text": "transfer outside Singapore",
                "evidence_chunk_ids": ["sg_p0_c1"],
                "token_overlap_score": 0.42,
            }
        ]
        out = enrich_recommendations(recs, CHUNKS)
        self.assertEqual(out[0]["token_overlap_score"], 0.42)
        self.assertEqual(out[0]["evidence_chunk_ids"], ["sg_p0_c1"])
        self.assertEqual(len(out[0]["evidence"]), 1)


class TestHumanReviewEscalation(unittest.TestCase):
    def test_clean_report_does_not_escalate(self) -> None:
        report = {
            "recommendations": [{"text": "x", "evidence_chunk_ids": ["sg_p0_c1"]}],
            "grounding": {"ok": True, "overlap": {"dropped_all": False}},
        }
        self.assertFalse(assess_human_review(report, CHUNKS)["needs_human_review"])

    def test_empty_retrieval_flags_weak_retrieval(self) -> None:
        out = assess_human_review({"grounding": {"ok": True}}, [])
        self.assertTrue(out["needs_human_review"])
        self.assertEqual(out["review_reason"], "weak_retrieval")

    def test_failed_grounding_flags_grounding_failed(self) -> None:
        report = {
            "recommendations": [{"text": "x", "evidence_chunk_ids": ["ghost"]}],
            "grounding": {"ok": False, "issues": ["Invalid evidence_chunk_ids"]},
        }
        out = assess_human_review(report, CHUNKS)
        self.assertEqual(out["review_reason"], "grounding_failed")
        self.assertIn("Invalid evidence_chunk_ids", out["review_details"])

    def test_overlap_dropping_everything_flags_low_overlap(self) -> None:
        report = {
            "recommendations": [],
            "grounding": {"ok": True, "overlap": {"dropped_all": True, "min_threshold": 0.06}},
        }
        out = assess_human_review(report, CHUNKS)
        self.assertEqual(out["review_reason"], "low_overlap")

    def test_partial_overlap_drop_also_flags_low_overlap(self) -> None:
        report = {
            "recommendations": [{"text": "supported", "evidence_chunk_ids": ["sg_p0_c1"]}],
            "grounding": {
                "ok": True,
                "overlap": {"dropped_all": False, "dropped_count": 1, "min_threshold": 0.06},
            },
        }
        out = assess_human_review(report, CHUNKS)
        self.assertEqual(out["review_reason"], "low_overlap")

    def test_skipped_overlap_does_not_trigger_low_overlap(self) -> None:
        # Offline fallback marks overlap as skipped; that is not a review trigger.
        report = {
            "recommendations": [{"text": "x", "evidence_chunk_ids": ["sg_p0_c1"]}],
            "grounding": {"ok": True, "overlap": {"skipped": True, "dropped_all": True}},
        }
        self.assertFalse(assess_human_review(report, CHUNKS)["needs_human_review"])

    def test_weak_retrieval_takes_priority_over_other_reasons(self) -> None:
        report = {"recommendations": [], "grounding": {"ok": False, "issues": ["no chunks"]}}
        out = assess_human_review(report, [])
        self.assertEqual(out["review_reason"], "weak_retrieval")
        self.assertIn("grounding_failed", out["review_reasons"])


class TestReportIntegration(unittest.TestCase):
    def test_apply_enrichment_adds_evidence_and_flags(self) -> None:
        report: Dict[str, Any] = {
            "recommendations": [
                {"text": "transfer outside Singapore", "evidence_chunk_ids": ["sg_p0_c1"]}
            ],
            "grounding": {"ok": True, "overlap": {"dropped_all": False}},
        }
        out = apply_phase3_enrichment(report, CHUNKS)
        self.assertIn("evidence", out["recommendations"][0])
        self.assertFalse(out["needs_human_review"])

    def test_empty_store_report_escalates_end_to_end(self) -> None:
        report = analyze_compliance(
            "Some consent text.",
            [],
            study_type="genomic_research",
            api_key=None,
        )
        self.assertTrue(report["needs_human_review"])
        self.assertEqual(report["review_reason"], "weak_retrieval")

    def test_offline_fallback_report_has_evidence(self) -> None:
        import os
        from unittest import mock

        # Force the offline keyword path: openai provider selected with no key.
        with mock.patch.dict(os.environ, {"REGBOT_LLM_PROVIDER": "openai"}):
            report = analyze_compliance(
                "This study shares genomic data with collaborators.",
                CHUNKS,
                study_type="genomic_research",
                api_key=None,
            )
        self.assertTrue(report["recommendations"])
        first = report["recommendations"][0]
        self.assertIn("evidence", first)
        self.assertTrue(first["evidence"][0]["quote"])
        self.assertFalse(report["grounding"]["overlap"].get("skipped", False))

        by_id = {chunk["id"]: chunk for chunk in CHUNKS}
        for recommendation in report["recommendations"]:
            evidence_id = recommendation["evidence_chunk_ids"][0]
            self.assertGreater(recommendation["token_overlap_score"], 0)
            self.assertNotEqual(by_id[evidence_id]["text"].strip(), "Table:")

    def test_offline_fallback_drops_unsupported_recommendations_and_escalates(self) -> None:
        import os
        from unittest import mock

        unrelated = [
            {
                "id": "table",
                "text": "Table appendix schedule contents index headings only.",
                "metadata": {"source": "x.pdf", "page": 1},
            }
        ]
        with mock.patch.dict(os.environ, {"REGBOT_LLM_PROVIDER": "openai"}):
            report = analyze_compliance(
                "Some consent text.",
                unrelated,
                study_type="genomic_research",
                api_key=None,
            )
        self.assertEqual(report["recommendations"], [])
        self.assertTrue(report["needs_human_review"])
        self.assertIn("low_overlap", report["review_reasons"])

    def test_offline_fallback_does_not_treat_generic_data_word_as_support(self) -> None:
        import os
        from unittest import mock

        generic = [
            {
                "id": "generic",
                "text": "Data records are listed in this appendix with administrative details.",
                "metadata": {"source": "x.pdf", "page": 1},
            }
        ]
        with mock.patch.dict(os.environ, {"REGBOT_LLM_PROVIDER": "openai"}):
            report = analyze_compliance(
                "Some consent text.",
                generic,
                study_type="genomic_research",
                api_key=None,
            )
        self.assertEqual(report["recommendations"], [])
        self.assertTrue(report["needs_human_review"])

    def test_ollama_client_disables_environment_proxies(self) -> None:
        import os
        from unittest import mock

        response = mock.Mock()
        response.choices = [mock.Mock(message=mock.Mock(content='{"recommendations": []}'))]
        completion = mock.Mock(return_value=response)
        client = mock.Mock()
        client.chat.completions.create = completion

        with (
            mock.patch.dict(os.environ, {"REGBOT_LLM_PROVIDER": "ollama"}),
            mock.patch("src.regbot.compliance.httpx.Client") as http_client,
            mock.patch("src.regbot.compliance.OpenAI", return_value=client),
        ):
            analyze_compliance(
                "Some consent text.",
                CHUNKS,
                study_type="genomic_research",
                api_key=None,
                max_grounding_retries=0,
            )

        http_client.assert_called_once_with(trust_env=False)


if __name__ == "__main__":
    unittest.main()
