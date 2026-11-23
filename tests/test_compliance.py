"""LLM response parsing through the production navigation-report retry loop."""

import json
import os
import unittest
from unittest import mock

from src.regbot.compliance import analyze_compliance

CHUNKS = [
    {
        "id": "policy_c1",
        "text": "Consent must be informed and voluntary.",
        "metadata": {"source": "policy.txt", "page": 0},
    }
]
VALID_RESPONSE = json.dumps(
    {
        "coverage": "partial",
        "recommendations": [
            {
                "text": "Consent must be informed and voluntary.",
                "evidence_chunk_ids": ["policy_c1"],
            }
        ],
    }
)
INVALID_RESPONSES = (
    '{"coverage": partial}',
    '```json\n{"coverage": partial}\n```',
    "[]",
    "null",
    "42",
    "true",
    '"not an object"',
    '[{"coverage": "complete"}]',
    "No JSON response is available.",
    "",
    None,
)


class TestComplianceResponseParsing(unittest.TestCase):
    def _analyze(self, contents, *, retries=1):
        responses = [
            mock.Mock(choices=[mock.Mock(message=mock.Mock(content=content))])
            for content in contents
        ]
        client = mock.Mock()
        completion = client.chat.completions.create
        completion.side_effect = responses
        with (
            mock.patch.dict(os.environ, {"REGBOT_LLM_PROVIDER": "openai"}),
            mock.patch("src.regbot.compliance.OpenAI", return_value=client),
        ):
            report = analyze_compliance(
                "Participants consent to genomic research.",
                CHUNKS,
                study_type="genomic_research",
                api_key="test-key",
                max_grounding_retries=retries,
            )
        return report, completion

    def test_invalid_response_can_be_corrected_within_retry_budget(self) -> None:
        for content in INVALID_RESPONSES:
            with self.subTest(content=content):
                report, completion = self._analyze([content, VALID_RESPONSE])
                self.assertEqual(completion.call_count, 2)
                self.assertEqual(report["grounding_attempts"], 2)
                self.assertTrue(report["grounding"]["ok"])
                self.assertFalse(report["needs_human_review"])
                self.assertEqual(report["recommendations"][0]["evidence_chunk_ids"], ["policy_c1"])
                correction = completion.call_args_list[1].kwargs["messages"][-1]["content"]
                self.assertIn("GROUNDING_FIX_REQUIRED", correction)
                self.assertIn("valid JSON object", correction)
                self.assertIn("Return the full JSON object again", correction)
                self.assertIn("policy_c1", correction)

    def test_repeated_invalid_responses_exhaust_retries_and_require_review(self) -> None:
        for content in INVALID_RESPONSES:
            with self.subTest(content=content):
                report, completion = self._analyze([content] * 3, retries=2)
                self.assertEqual(completion.call_count, 3)
                self.assertEqual(report["grounding_attempts"], 3)
                self.assertEqual(report["coverage"], "unknown")
                self.assertEqual(report["recommendations"], [])
                self.assertFalse(report["grounding"]["ok"])
                self.assertTrue(report["needs_human_review"])
                self.assertEqual(report["review_reason"], "grounding_failed")
                self.assertTrue(
                    any("valid JSON object" in issue for issue in report["grounding"]["issues"])
                )

    def test_zero_retries_makes_one_attempt(self) -> None:
        report, completion = self._analyze(['{"coverage": partial}'], retries=0)
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(report["grounding_attempts"], 1)
        self.assertFalse(report["grounding"]["ok"])
        self.assertEqual(report["review_reason"], "grounding_failed")

    def test_valid_plain_and_fenced_objects_are_accepted_without_retry(self) -> None:
        for content in (VALID_RESPONSE, f"```json\n{VALID_RESPONSE}\n```"):
            with self.subTest(content=content):
                report, completion = self._analyze([content])
                self.assertEqual(completion.call_count, 1)
                self.assertEqual(report["grounding_attempts"], 1)
                self.assertEqual(report["coverage"], "partial")
                self.assertTrue(report["grounding"]["ok"])
                self.assertFalse(report["needs_human_review"])


if __name__ == "__main__":
    unittest.main()
