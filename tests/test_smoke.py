import tempfile
import unittest

from src.main import RegBot
from src.regbot.compliance import normalize_coverage


class TestRegBotSmoke(unittest.TestCase):
    def test_instantiates(self) -> None:
        bot = RegBot(api_key="test", store_dir=tempfile.mkdtemp())
        self.assertEqual(bot.api_key, "test")

    def test_empty_store_retrieval(self) -> None:
        bot = RegBot(store_dir=tempfile.mkdtemp())
        self.assertEqual(bot.retrieve_relevant_clauses("anything"), [])

    def test_normalize_coverage_maps_legacy_status(self) -> None:
        self.assertEqual(normalize_coverage("Non-Compliant"), "incomplete")
        self.assertEqual(normalize_coverage("partial"), "partial")
        self.assertEqual(normalize_coverage("Compliant"), "complete")

    def test_check_without_store(self) -> None:
        bot = RegBot(store_dir=tempfile.mkdtemp())
        report = bot.check_compliance("short consent text about genomics and sharing")
        self.assertIsInstance(report, dict)
        self.assertIn("coverage", report)
        self.assertNotIn("status", report)
        self.assertIn("grounding", report)


if __name__ == "__main__":
    unittest.main()
