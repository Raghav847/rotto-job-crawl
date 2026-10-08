import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crawler.dedupe import Decision, backfill, compare, deduplicate_listing, profile
from crawler.models import Observation
from crawler.reconcile import reconcile, stored_rows
from tests.support import isolated_database


FIXTURE = json.loads((Path(__file__).with_name("fixtures") / "dedupe_pairs.json").read_text())
CLOCK = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)


def listing(source, identity, changes=None):
    values = {**FIXTURE["base"], **(changes or {})}
    description = FIXTURE["descriptions"][values.pop("description_key")]
    description += values.pop("description_suffix", "")
    return {"id": f"{source}:{identity}", "source": source, "source_job_id": identity,
            "url": f"https://example.invalid/{source}/{identity}", "company_logo_url": None,
            "posted_at": CLOCK, "description": description, "removed_at": None, **values}


class PairMatchingTests(unittest.TestCase):
    def test_labelled_positive_and_negative_pairs(self):
        true_positive = false_positive = false_negative = 0
        for pair in FIXTURE["pairs"]:
            left = profile(listing("reed", "left", pair["left"]))
            right = profile(listing("linkedin", "right", pair["right"]))
            decision = compare(left, right)
            with self.subTest(pair=pair["name"], reason=decision.reason, scores=decision.scores):
                self.assertEqual(decision.matched, pair["duplicate"])
            true_positive += int(decision.matched and pair["duplicate"])
            false_positive += int(decision.matched and not pair["duplicate"])
            false_negative += int(not decision.matched and pair["duplicate"])
        precision = true_positive / (true_positive + false_positive)
        recall = true_positive / (true_positive + false_negative)
        self.assertEqual(precision, 1.0)
        self.assertEqual(recall, 1.0)

    def test_same_board_needs_requisition_evidence(self):
        left = listing("reed", "one")
        right = listing("reed", "two")
        self.assertFalse(compare(profile(left), profile(right)).matched)
        left["description"] += "\nJob reference: PAY-2026-7741"
        right["description"] += "\nJob reference: PAY-2026-7741"
        self.assertTrue(compare(profile(left), profile(right)).matched)

    def test_explicit_different_postcode_areas_are_not_merged(self):
        left = profile(listing("reed", "one", {"location": "London E1 6AN"}))
        right = profile(listing("linkedin", "two", {"location": "London SW1A 1AA"}))
        self.assertFalse(compare(left, right).matched)


class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.connection = self.enterContext(isolated_database())

    def apply(self, source, identity, hour=0, changes=None):
        observation = Observation.from_dict({"source": source, "scope": "dedupe-test",
                                            "observed_at": CLOCK + timedelta(hours=hour),
                                            "details": [listing(source, identity, changes)]})
        return reconcile(self.connection, observation)

    def rows(self):
        return stored_rows(self.connection)

    def test_cross_board_copies_join_oldest_group_without_lifecycle_changes(self):
        self.apply("reed", "first")
        before = self.rows()["reed:first"]
        self.assertEqual(self.apply("linkedin", "second", 1), {"jobs_new": 1, "jobs_changed": 0, "jobs_removed": 0})
        rows = self.rows()
        self.assertEqual(rows["linkedin:second"]["canonical_job_id"], before["canonical_job_id"])
        self.assertEqual(rows["reed:first"], before)
        self.assertEqual(self.apply("linkedin", "second", 1), {"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
        self.assertEqual(self.rows(), rows)
        self.assertEqual(backfill(self.connection), 0)

    def test_description_edit_preserves_known_identity_when_not_contradictory(self):
        self.apply("reed", "first")
        self.apply("linkedin", "second", 1)
        identity = self.rows()["reed:first"]["canonical_job_id"]
        result = self.apply("linkedin", "second", 2, {"description_key": "reworded"})
        self.assertEqual(result["jobs_changed"], 1)
        self.assertEqual(self.rows()["linkedin:second"]["canonical_job_id"], identity)

    def test_third_board_copy_joins_same_stable_group(self):
        self.apply("reed", "first")
        self.apply("linkedin", "second", 1)
        self.apply("indeed", "third", 2)
        self.assertEqual(len({row["canonical_job_id"] for row in self.rows().values()}), 1)

    def test_duplicate_group_updates_roll_back_with_the_listing(self):
        self.apply("reed", "first")
        before = self.rows()
        with self.assertRaises(RuntimeError):
            with self.connection.transaction():
                self.apply("linkedin", "second", 1)
                raise RuntimeError("Interrupted transaction")
        self.assertEqual(self.rows(), before)

    def test_definitive_company_change_splits_only_edited_listing(self):
        self.apply("reed", "first")
        self.apply("linkedin", "second", 1)
        before = self.rows()
        result = self.apply("reed", "first", 2, {"company": "Other Employer Ltd"})
        after = self.rows()
        self.assertEqual(result["jobs_changed"], 1)
        self.assertEqual(after["linkedin:second"]["canonical_job_id"], before["linkedin:second"]["canonical_job_id"])
        self.assertNotEqual(after["reed:first"]["canonical_job_id"], after["linkedin:second"]["canonical_job_id"])
        self.assertEqual(after["reed:first"]["first_seen_at"], before["reed:first"]["first_seen_at"])

    def test_removal_and_reappearance_keep_shared_identity(self):
        self.apply("reed", "first")
        self.apply("linkedin", "second", 1)
        before = self.rows()
        removed = Observation.from_dict({"source": "reed", "observed_at": CLOCK + timedelta(hours=2),
                                         "confirmed_removed_source_job_ids": ["first"]})
        reconcile(self.connection, removed)
        self.apply("reed", "first", 3)
        row = self.rows()["reed:first"]
        self.assertIsNone(row["removed_at"])
        self.assertEqual(row["canonical_job_id"], before["reed:first"]["canonical_job_id"])

    def test_weak_transitive_bridge_does_not_merge_incompatible_endpoints(self):
        self.apply("reed", "a")
        self.apply("linkedin", "b", 1)
        old_group = self.rows()["reed:a"]["canonical_job_id"]
        real_compare = compare

        def chain(left, right):
            if {left["id"], right["id"]} == {"reed:a", "indeed:c"}:
                return Decision(False, "synthetic_incompatible_endpoints", {})
            return real_compare(left, right)

        with patch("crawler.dedupe.compare", side_effect=chain):
            self.apply("indeed", "c", 2)
        rows = self.rows()
        self.assertEqual(rows["reed:a"]["canonical_job_id"], old_group)
        self.assertEqual(rows["linkedin:b"]["canonical_job_id"], old_group)
        self.assertNotEqual(rows["indeed:c"]["canonical_job_id"], old_group)


if __name__ == "__main__":
    unittest.main()
