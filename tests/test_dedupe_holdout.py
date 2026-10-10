import json
import unittest
from pathlib import Path

from crawler.dedupe_review import evaluate


class HoldoutTests(unittest.TestCase):
    def test_independent_negatives_and_unresolved_labels_are_distinguished(self):
        fixture = json.loads((Path(__file__).with_name("fixtures") / "dedupe_holdout_pairs.json").read_text())
        result = evaluate(fixture)
        self.assertEqual(result["false_positive"], 0)
        self.assertEqual(result["true_negative"], len([pair for pair in fixture["pairs"] if pair["duplicate"] is False]))
        self.assertIsNone(result["recall"])
        self.assertEqual(len(result["unresolved"]), 1)
