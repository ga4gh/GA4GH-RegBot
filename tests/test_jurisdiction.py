"""Tests for jurisdiction metadata and retrieval filtering."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from src.regbot.ingestion import ingest_policy_file, read_manifest
from src.regbot.jurisdiction import (
    jurisdiction_matches,
    jurisdictions_in_manifest,
    parse_jurisdiction_filter,
)
from src.regbot.retrieval import HybridRetriever


class _FakeEmbeddings:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class _FakeSentenceTransformer:
    def encode(self, texts, normalize_embeddings=True):  # noqa: ARG002
        if isinstance(texts, str):
            n = 1
        else:
            n = len(texts)
        return _FakeEmbeddings([[1.0] * 384 for _ in range(n)])


class TestJurisdiction(unittest.TestCase):
    def test_parse_filter_empty(self) -> None:
        self.assertIsNone(parse_jurisdiction_filter(None))
        self.assertIsNone(parse_jurisdiction_filter([]))

    def test_jurisdiction_matches(self) -> None:
        meta = {"jurisdiction": "JP"}
        self.assertTrue(jurisdiction_matches(meta, ["JP"]))
        self.assertFalse(jurisdiction_matches(meta, ["SG"]))
        self.assertTrue(jurisdiction_matches(meta, None))

    @patch("src.regbot.ingestion.load_sentence_transformer")
    def test_ingest_tags_jurisdiction(self, mock_load) -> None:
        mock_load.return_value = _FakeSentenceTransformer()
        with tempfile.TemporaryDirectory() as store:
            policy = (
                "Genomic data may be shared internationally subject to ethics review "
                "and participant withdrawal rights."
            )
            path = f"{store}/sg_policy.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(policy)
            ingest_policy_file(path, store, jurisdiction="sg", reset=True)
            chunks = read_manifest(store)
            self.assertGreater(len(chunks), 0)
            self.assertEqual(chunks[0]["metadata"].get("jurisdiction"), "SG")
            codes = jurisdictions_in_manifest(chunks)
            self.assertEqual(codes, ["SG"])

    @patch("src.regbot.retrieval.load_sentence_transformer")
    @patch("src.regbot.ingestion.load_sentence_transformer")
    def test_retrieval_jurisdiction_filter(self, mock_ingest_load, mock_retrieve_load) -> None:
        fake = _FakeSentenceTransformer()
        mock_ingest_load.return_value = fake
        mock_retrieve_load.return_value = fake
        with tempfile.TemporaryDirectory() as store:
            for region, text in (
                ("SG", "Singapore PDPA personal data protection and cross-border transfer."),
                ("JP", "Japan APPI act on protection of personal information genomic research."),
            ):
                path = f"{store}/{region.lower()}.txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                ingest_policy_file(
                    path,
                    store,
                    jurisdiction=region,
                    reset=(region == "SG"),
                )
            r = HybridRetriever(store)
            self.assertEqual(sorted(r.list_jurisdictions()), ["JP", "SG"])
            all_hits = r.retrieve("personal data protection", top_k=8)
            self.assertGreaterEqual(len(all_hits), 1)
            sg_only = r.retrieve(
                "personal data protection",
                top_k=8,
                jurisdiction=["SG"],
            )
            for hit in sg_only:
                self.assertEqual(hit["metadata"].get("jurisdiction"), "SG")


if __name__ == "__main__":
    unittest.main()
