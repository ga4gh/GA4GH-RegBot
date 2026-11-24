from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from src.main import RegBot


class _FakeEmbeddings:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class _FakeSentenceTransformer:
    def __init__(self, *args, **kwargs):  # noqa: ARG002
        pass

    def encode(self, texts, normalize_embeddings=True):  # noqa: ARG002
        if isinstance(texts, str):
            n = 1
        else:
            n = len(texts)
        return _FakeEmbeddings([[1.0] * 384 for _ in range(n)])


class TestRegBotPipeline(unittest.TestCase):
    def setUp(self) -> None:
        # Default app uses Ollama; this test expects offline heuristic (no running Ollama).
        self._saved_provider = os.environ.get("REGBOT_LLM_PROVIDER")
        os.environ["REGBOT_LLM_PROVIDER"] = "openai"

    def tearDown(self) -> None:
        if self._saved_provider is None:
            os.environ.pop("REGBOT_LLM_PROVIDER", None)
        else:
            os.environ["REGBOT_LLM_PROVIDER"] = self._saved_provider

    @patch("src.regbot.retrieval.load_sentence_transformer")
    @patch("src.regbot.ingestion.load_sentence_transformer")
    def test_ingest_retrieve_check_smoke(self, mock_ingest_load, mock_retrieve_load) -> None:
        fake = _FakeSentenceTransformer()
        mock_ingest_load.return_value = fake
        mock_retrieve_load.return_value = fake
        policy = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "data"
            / "sample_ga4gh_policy_stub.txt"
        )
        consent = (
            Path(__file__).resolve().parents[1] / "examples" / "data" / "sample_consent_short.txt"
        )
        self.assertTrue(policy.is_file(), "missing examples/data sample policy file")

        with tempfile.TemporaryDirectory() as tmp:
            bot = RegBot(store_dir=tmp, api_key="")
            self.assertTrue(bot.ingest_policy_documents(str(policy), reset=True))
            hits = bot.retrieve_relevant_clauses("international data sharing withdrawal", top_k=4)
            self.assertGreater(len(hits), 0)
            self.assertIn("id", hits[0])
            with open(consent, encoding="utf-8") as f:
                report = bot.check_compliance(f.read(), top_k=6)
            self.assertIn("coverage", report)
            self.assertNotIn("status", report)
            self.assertIn("citations", report)
            self.assertIsInstance(report["recommendations"], list)
            self.assertGreater(len(report["recommendations"]), 0)
            self.assertIn("text", report["recommendations"][0])
            self.assertIn("evidence_chunk_ids", report["recommendations"][0])
            self.assertIn("grounding", report)


class TestRegBotStoreRefresh(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        fake = _FakeSentenceTransformer()
        for module in ("ingestion", "retrieval"):
            self.enterContext(
                patch(f"src.regbot.{module}.load_sentence_transformer", return_value=fake)
            )

    def _policy(self, root: Path, name: str, text: str | None = None) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        path.write_text(
            text
            if text is not None
            else "Participants must provide informed consent before research data may be shared "
            "internationally with approved institutions.",
            encoding="utf-8",
        )
        return path

    def _primed_bot(self, root: Path) -> RegBot:
        old = self._policy(root, "old.txt")
        bot = RegBot(store_dir=str(root / "store"), api_key="")
        self.assertTrue(bot.ingest_policy_documents(str(old), jurisdiction="SG"))
        hits = bot.retrieve_relevant_clauses("participant consent")
        self.assertEqual([hit["metadata"]["source"] for hit in hits], ["old.txt"])
        return bot

    def _assert_updated_sources(self, bot: RegBot, *, reset: bool) -> None:
        scoped = bot.retrieve_relevant_clauses("participant consent", jurisdiction=["EU"])
        self.assertEqual([hit["metadata"]["source"] for hit in scoped], ["new.txt"])
        all_hits = bot.retrieve_relevant_clauses("participant consent")
        expected = {"new.txt"} if reset else {"old.txt", "new.txt"}
        self.assertEqual({hit["metadata"]["source"] for hit in all_hits}, expected)

    def test_single_file_ingestion_refreshes_cached_retrieval(self) -> None:
        for reset in (False, True):
            with self.subTest(reset=reset):
                root = self.root / str(reset)
                bot = self._primed_bot(root)
                new = self._policy(root, "new.txt")
                self.assertTrue(
                    bot.ingest_policy_documents(str(new), jurisdiction="EU", reset=reset)
                )
                self._assert_updated_sources(bot, reset=reset)

    def test_manifest_ingestion_refreshes_cached_retrieval(self) -> None:
        for reset in (False, True):
            with self.subTest(reset=reset):
                root = self.root / str(reset)
                bot = self._primed_bot(root)
                new = self._policy(root, "new.txt")
                manifest = root / "corpus.yaml"
                manifest.write_text(
                    yaml.safe_dump(
                        {
                            "documents": [
                                {
                                    "document_id": "new-policy",
                                    "tier": "P0",
                                    "jurisdiction": ["EU"],
                                    "ingest_path": str(new),
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                summary = bot.ingest_from_manifest(str(manifest), reset=reset)
                self.assertEqual(summary["ingested"], 1)
                self.assertEqual(summary["errors"], 0)
                self._assert_updated_sources(bot, reset=reset)

    def test_failed_reset_does_not_return_deleted_cached_chunks(self) -> None:
        for raise_on_error in (False, True):
            with self.subTest(raise_on_error=raise_on_error):
                root = self.root / str(raise_on_error)
                bot = self._primed_bot(root)
                blank = self._policy(root, "blank.txt", "   \n")
                if raise_on_error:
                    with self.assertRaises(ValueError):
                        bot.ingest_policy_documents(str(blank), reset=True, raise_on_error=True)
                else:
                    self.assertFalse(bot.ingest_policy_documents(str(blank), reset=True))
                self.assertFalse(bot.is_retrieval_ready())
                self.assertEqual(bot.retrieve_relevant_clauses("participant consent"), [])


if __name__ == "__main__":
    unittest.main()
