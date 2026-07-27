"""
API-layer tests. The API is the contract the Next.js UI depends on, so these pin the
response shapes and the input validation — no LLM and no embedding model required.
"""

import json
import os
import tempfile
import unittest
from typing import Any, Dict, List
from unittest import mock

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "sg_c0",
        "text": "Organisations must not transfer personal data outside Singapore.",
        "metadata": {
            "source": "pdpa-hbra-excerpt.txt",
            "page": 0,
            "document_id": "sg-law-excerpt",
            "jurisdiction": "SG",
            "framework": "national",
        },
    },
    {
        "id": "eu_c0",
        "text": "Article 35 requires a Data Protection Impact Assessment.",
        "metadata": {
            "source": "gdpr-dpia.txt",
            "page": 0,
            "document_id": "gdpr-dpia-genomic-research",
            "jurisdiction": "EU",
            "framework": "GDPR",
        },
    },
]


def _store_with_manifest() -> str:
    """Create a temp store containing only manifest.json (no Chroma, no embeddings)."""
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"chunks": CHUNKS}, f)
    return tmp


class TestMetaEndpoints(unittest.TestCase):
    def test_health(self) -> None:
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_jurisdictions_cover_the_rews_regional_scope(self) -> None:
        r = client.get("/api/meta/jurisdictions")
        self.assertEqual(r.status_code, 200)
        codes = {row["code"] for row in r.json()}
        self.assertTrue({"SG", "CN", "TW", "KR", "JP", "HK", "EU", "GA4GH"} <= codes)

    def test_store_meta_reports_resolved_directory(self) -> None:
        r = client.get("/api/meta/store", params={"store_dir": "./data/regbot_store"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["store_dir"], "./data/regbot_store")


class TestCorpusEndpoint(unittest.TestCase):
    def test_lists_corpus_documents(self) -> None:
        r = client.get("/api/corpus")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreater(body["total"], 0)
        self.assertEqual(body["total"], len(body["documents"]))
        self.assertTrue(all(d["document_id"] for d in body["documents"]))

    def test_region_filter_narrows_results(self) -> None:
        every = client.get("/api/corpus").json()["total"]
        only_sg = client.get("/api/corpus", params={"region": "SG"}).json()
        self.assertLess(only_sg["total"], every)
        for doc in only_sg["documents"]:
            self.assertIn("SG", doc["jurisdiction"])

    def test_all_region_is_not_treated_as_a_filter(self) -> None:
        every = client.get("/api/corpus").json()["total"]
        self.assertEqual(client.get("/api/corpus", params={"region": "ALL"}).json()["total"], every)


class TestChunksEndpoint(unittest.TestCase):
    def test_rejects_unknown_jurisdiction(self) -> None:
        r = client.get("/api/chunks", params={"region": "ZZ"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Unknown jurisdiction", r.json()["detail"])

    def test_filters_manifest_by_region(self) -> None:
        store = _store_with_manifest()
        r = client.get("/api/chunks", params={"region": "SG", "store_dir": store})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["region"], "SG")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["chunks"][0]["id"], "sg_c0")

    def test_limit_bounds_are_enforced(self) -> None:
        store = _store_with_manifest()
        self.assertEqual(
            client.get(
                "/api/chunks", params={"region": "SG", "limit": 0, "store_dir": store}
            ).status_code,
            422,
        )
        self.assertEqual(
            client.get(
                "/api/chunks", params={"region": "SG", "limit": 999, "store_dir": store}
            ).status_code,
            422,
        )


class TestIngestEndpoint(unittest.TestCase):
    def test_rejects_unsupported_extension(self) -> None:
        r = client.post(
            "/api/ingest",
            files={"file": ("policy.docx", b"data", "application/octet-stream")},
            data={"jurisdiction": "SG"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Only PDF and .txt", r.json()["detail"])

    def test_rejects_unknown_jurisdiction_before_reading_the_file(self) -> None:
        r = client.post(
            "/api/ingest",
            files={"file": ("policy.txt", b"text", "text/plain")},
            data={"jurisdiction": "ZZ"},
        )
        self.assertEqual(r.status_code, 400)


class TestCheckEndpoint(unittest.TestCase):
    def test_rejects_empty_consent_text(self) -> None:
        r = client.post("/api/check", json={"consent_text": "   "})
        self.assertEqual(r.status_code, 400)

    def test_returns_report_with_phase3_fields(self) -> None:
        report = {
            "study_type": "genomic_research",
            "coverage": "partial",
            "recommendations": [
                {
                    "text": "Clarify cross-border transfer.",
                    "evidence_chunk_ids": ["sg_c0"],
                    "evidence": [{"chunk_id": "sg_c0", "resolved": True, "quote": "…"}],
                }
            ],
            "grounding": {"ok": True},
            "needs_human_review": False,
        }
        with mock.patch(
            "src.main.RegBot.compliance_report_and_chunks",
            return_value=(report, CHUNKS[:1]),
        ):
            r = client.post(
                "/api/check",
                json={"consent_text": "We share genomic data.", "jurisdictions": ["SG"]},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["chunk_count"], 1)
        self.assertEqual(body["scope"], "SG")
        self.assertIn("evidence", body["report"]["recommendations"][0])
        self.assertFalse(body["report"]["needs_human_review"])

    def test_scope_label_when_no_filter_selected(self) -> None:
        with mock.patch(
            "src.main.RegBot.compliance_report_and_chunks",
            return_value=({"coverage": "unknown"}, []),
        ):
            r = client.post("/api/check", json={"consent_text": "text"})
        self.assertEqual(r.json()["scope"], "all jurisdictions")


class TestChatEndpoint(unittest.TestCase):
    def test_empty_messages_prompts_for_input(self) -> None:
        r = client.post("/api/chat", json={"messages": []})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Please enter a question", r.json()["reply"])

    def test_no_matching_chunks_explains_instead_of_failing(self) -> None:
        with mock.patch("src.main.RegBot.retrieve_relevant_clauses", return_value=[]):
            r = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "What about transfers?"}]},
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("No policy chunks matched", r.json()["reply"])

    def test_uses_supplied_chunks_without_re_retrieving(self) -> None:
        with (
            mock.patch("src.main.RegBot.retrieve_relevant_clauses") as retrieve,
            mock.patch("src.api.app.chat_followup_policy_qa", return_value="grounded answer"),
        ):
            r = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Transfers?"}],
                    "chunks": CHUNKS,
                },
            )
        retrieve.assert_not_called()
        self.assertEqual(r.json()["reply"], "grounded answer")


if __name__ == "__main__":
    unittest.main()
