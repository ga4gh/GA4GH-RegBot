import tempfile
import unittest

from src.main import RegBot


class TestRegBotSmoke(unittest.TestCase):
    def test_instantiates(self) -> None:
        bot = RegBot(api_key="test", store_dir=tempfile.mkdtemp())
        self.assertEqual(bot.api_key, "test")

    def test_empty_store_retrieval(self) -> None:
        bot = RegBot(store_dir=tempfile.mkdtemp())
        self.assertEqual(bot.retrieve_relevant_clauses("anything"), [])

    def test_check_without_store(self) -> None:
        bot = RegBot(store_dir=tempfile.mkdtemp())
        report = bot.check_compliance("short consent text about genomics and sharing")
        self.assertIsInstance(report, dict)
        self.assertIn("status", report)
        self.assertIn("grounding", report)


if __name__ == "__main__":
    unittest.main()
