"""Benchmark CLI gates, without a vector store, embedding model, or network calls."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from typing import Any
from unittest.mock import patch

from src import main as cli

CHUNKS: list[dict[str, Any]] = [
    {
        "id": "policy_p1_c0",
        "text": "Participants may withdraw consent.",
        "metadata": {"document_id": "policy", "page": 1},
    },
    {
        "id": "policy_p2_c1",
        "text": "Transfers require safeguards.",
        "metadata": {"document_id": "policy", "page": 2},
    },
]
VALID_ANCHOR = {"document_id": "policy", "contains": "withdraw consent"}
STALE_ANCHOR = {"document_id": "policy", "contains": "no longer in the corpus"}


def _gold(*anchors: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "test",
        "queries": [
            {"query_id": "q1", "query": "withdrawal and transfers", "relevant": list(anchors)}
        ],
    }


class TestBenchmarkCli(unittest.TestCase):
    def _run(
        self,
        gold: dict[str, Any],
        *options: str,
        hits: list[dict[str, Any]] | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        args = cli.build_parser().parse_args(["--store", "stub-store", "benchmark", *options])
        self.assertIs(args.func, cli._cmd_benchmark)
        ranking = CHUNKS if hits is None else hits
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "RegBot") as bot_class,
            patch.object(cli, "read_manifest", return_value=CHUNKS),
            patch.object(cli, "load_gold_set", return_value=gold),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            bot = bot_class.return_value
            bot.store_dir = "stub-store"
            bot.retrieve_relevant_clauses.side_effect = (
                lambda query, *, top_k, jurisdiction: ranking[:top_k]
            )
            exit_code = args.func(args)
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_partially_unresolved_query_fails_even_with_perfect_resolved_recall(self) -> None:
        code, result, stderr = self._run(_gold(VALID_ANCHOR, STALE_ANCHOR))
        self.assertEqual(result["query_count"], 1)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(result["unresolved_anchor_count"], 1)
        self.assertEqual(result["aggregate"]["provision_recall@8"], 1.0)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", stderr)

    def test_fully_unresolved_query_fails_without_a_metric_threshold(self) -> None:
        code, result, _ = self._run(_gold(STALE_ANCHOR))
        self.assertEqual(result["query_count"], 0)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["unresolved_anchor_count"], 1)
        self.assertEqual(code, 1)

    def test_unlabelled_query_cannot_silently_shrink_the_scoring_set(self) -> None:
        for relevant in ([], None, ["invalid-anchor"]):
            with self.subTest(relevant=relevant):
                gold = _gold(VALID_ANCHOR)
                gold["queries"].append(
                    {"query_id": "q2", "query": "missing label", "relevant": relevant}
                )
                code, result, _ = self._run(gold, "--min-provision-recall", "0.90")
                self.assertEqual(result["query_count"], 1)
                self.assertEqual(result["skipped_count"], 1)
                self.assertEqual(result["unresolved_anchor_count"], 0)
                self.assertEqual(result["aggregate"]["provision_recall@8"], 1.0)
                self.assertEqual(code, 1)

    def test_empty_gold_fails_even_without_a_metric_threshold(self) -> None:
        code, result, _ = self._run({"queries": []})
        self.assertEqual(result["query_count"], 0)
        self.assertEqual(result["unresolved_anchor_count"], 0)
        self.assertEqual(code, 1)

    def test_recall_below_either_threshold_fails(self) -> None:
        gold = _gold(VALID_ANCHOR, {"document_id": "policy", "contains": "safeguards"})
        for option in ("--min-recall", "--min-provision-recall"):
            with self.subTest(option=option):
                code, result, stderr = self._run(gold, option, "0.6", hits=CHUNKS[:1])
                self.assertEqual(result["aggregate"]["recall@8"], 0.5)
                self.assertEqual(result["aggregate"]["provision_recall@8"], 0.5)
                self.assertEqual(code, 1)
                self.assertIn("FAIL", stderr)

    def test_recall_equal_to_either_threshold_passes(self) -> None:
        gold = _gold(VALID_ANCHOR, {"document_id": "policy", "contains": "safeguards"})
        for option in ("--min-recall", "--min-provision-recall"):
            with self.subTest(option=option):
                code, _, stderr = self._run(gold, option, "0.5", hits=CHUNKS[:1])
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")

    def test_gate_uses_largest_requested_k(self) -> None:
        gold = _gold(VALID_ANCHOR, {"document_id": "policy", "contains": "safeguards"})
        code, result, _ = self._run(
            gold, "--ks", "2,1", "--min-recall", "1", "--min-provision-recall", "1"
        )
        self.assertEqual(result["aggregate"]["provision_recall@1"], 0.5)
        self.assertEqual(result["aggregate"]["provision_recall@2"], 1.0)
        self.assertEqual(code, 0)

    def test_valid_gold_without_a_threshold_remains_report_only(self) -> None:
        code, result, stderr = self._run(_gold(VALID_ANCHOR), hits=[])
        self.assertEqual(result["aggregate"]["provision_recall@8"], 0.0)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")


class TestBenchmarkThresholdArguments(unittest.TestCase):
    def test_rejects_nonfinite_and_out_of_range_thresholds(self) -> None:
        parser = cli.build_parser()
        for option in ("--min-recall", "--min-provision-recall"):
            for value in ("nan", "NaN", "inf", "-inf", "-0.01", "1.01"):
                with self.subTest(option=option, value=value):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                        parser.parse_args(["benchmark", f"{option}={value}"])
                    self.assertEqual(error.exception.code, 2)
                    self.assertIn(option, stderr.getvalue())

    def test_accepts_probability_boundaries_and_default_gate(self) -> None:
        parser = cli.build_parser()
        for option in ("--min-recall", "--min-provision-recall"):
            for value in ("0", "0.90", "1"):
                with self.subTest(option=option, value=value):
                    args = parser.parse_args(["benchmark", f"{option}={value}"])
                    self.assertEqual(getattr(args, option[2:].replace("-", "_")), float(value))


if __name__ == "__main__":
    unittest.main()
