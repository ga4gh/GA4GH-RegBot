"""Tests for corpus_manifest batch ingest."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import yaml

from src.regbot.corpus_manifest import (
    ingest_from_corpus_manifest,
    load_corpus_manifest,
    primary_jurisdiction,
    resolve_ingest_path,
)
from src.regbot.ingestion import read_manifest


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


class TestCorpusManifest(unittest.TestCase):
    def test_primary_jurisdiction_prefers_non_intl(self) -> None:
        self.assertEqual(primary_jurisdiction(["GA4GH", "INTL"]), "GA4GH")
        self.assertEqual(primary_jurisdiction(["INTL"]), "INTL")
        self.assertIsNone(primary_jurisdiction([]))

    def test_resolve_ingest_path_relative_to_repo(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            docs_dir = os.path.join(root, "docs")
            os.makedirs(docs_dir)
            corpus_file = os.path.join(root, "data", "sample.txt")
            os.makedirs(os.path.dirname(corpus_file), exist_ok=True)
            with open(corpus_file, "w", encoding="utf-8") as f:
                f.write("x")
            manifest = os.path.join(docs_dir, "corpus_manifest.yaml")
            resolved = resolve_ingest_path("data/sample.txt", manifest_path=manifest)
            self.assertTrue(os.path.samefile(resolved, corpus_file))

    @patch("src.regbot.ingestion.load_sentence_transformer")
    def test_batch_ingest_updates_manifest_and_metadata(self, mock_load) -> None:
        mock_load.return_value = _FakeSentenceTransformer()
        with tempfile.TemporaryDirectory() as root:
            docs_dir = os.path.join(root, "docs")
            store_dir = os.path.join(root, "store")
            corpus_dir = os.path.join(root, "data", "corpus", "P0")
            os.makedirs(docs_dir)
            os.makedirs(corpus_dir)
            policy_path = os.path.join(corpus_dir, "ga4gh-frs-en.txt")
            with open(policy_path, "w", encoding="utf-8") as f:
                f.write(
                    "Framework for responsible sharing of genomic and health-related data. "
                    "Participants must be informed of international data transfers."
                )
            manifest_path = os.path.join(docs_dir, "corpus_manifest.yaml")
            manifest_data = {
                "version": "0.1",
                "updated": None,
                "documents": [
                    {
                        "document_id": "ga4gh-frs",
                        "tier": "P0",
                        "jurisdiction": ["GA4GH", "INTL"],
                        "framework": "GA4GH",
                        "ingest_path": "data/corpus/P0/ga4gh-frs-en.txt",
                        "ingested_at": None,
                    }
                ],
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(manifest_data, f)

            summary = ingest_from_corpus_manifest(
                manifest_path,
                store_dir,
                reset=True,
            )
            self.assertEqual(summary["ingested"], 1)
            self.assertEqual(summary["results"][0]["status"], "ok")

            reloaded = load_corpus_manifest(manifest_path)
            self.assertIsNotNone(reloaded["documents"][0]["ingested_at"])
            self.assertIsNotNone(reloaded["updated"])

            chunks = read_manifest(store_dir)
            self.assertGreater(len(chunks), 0)
            meta = chunks[0]["metadata"]
            self.assertEqual(meta.get("document_id"), "ga4gh-frs")
            self.assertEqual(meta.get("framework"), "GA4GH")
            self.assertEqual(meta.get("jurisdiction"), "GA4GH")
            self.assertEqual(meta.get("category"), "ga4gh-frs")

    def test_dry_run_does_not_write_manifest_or_store(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            docs_dir = os.path.join(root, "docs")
            os.makedirs(docs_dir)
            manifest_path = os.path.join(docs_dir, "corpus_manifest.yaml")
            manifest_data = {
                "version": "0.1",
                "documents": [
                    {
                        "document_id": "missing-doc",
                        "tier": "P0",
                        "jurisdiction": ["GA4GH"],
                        "ingest_path": "data/corpus/P0/does-not-exist.pdf",
                        "ingested_at": None,
                    }
                ],
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(manifest_data, f)

            summary = ingest_from_corpus_manifest(
                manifest_path,
                os.path.join(root, "store"),
                dry_run=True,
            )
            self.assertEqual(summary["results"][0]["status"], "missing_file")
            reloaded = load_corpus_manifest(manifest_path)
            self.assertIsNone(reloaded["documents"][0]["ingested_at"])


if __name__ == "__main__":
    unittest.main()
