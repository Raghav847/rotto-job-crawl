import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crawler.dedupe import compare, profile
from crawler.dedupe_review import evaluate
from crawler.models import Listing, Observation
from crawler.reconcile import reconcile, stored_rows
from tests.support import isolated_database


FIXTURE = json.loads((Path(__file__).with_name("fixtures") / "real_dedupe_pairs.json").read_text())
CLOCK = datetime(2026, 10, 9, 6, tzinfo=timezone.utc)
TESCO = "linkedin:4470379586"
TECHNOLOGY = "linkedin:4470374657"


def row(identity):
    raw = copy.deepcopy(FIXTURE["rows"][identity])
    return {**raw, **Listing.from_dict(raw).content}


class RealPairTests(unittest.TestCase):
    def test_all_independently_labelled_pairs(self):
        result = evaluate(FIXTURE)
        for decision in result["decisions"]:
            with self.subTest(pair=decision["name"], reason=decision["reason"]):
                self.assertEqual(decision["matched"], decision["expected_duplicate"])
        self.assertEqual(result["false_positive"], 0)
        self.assertEqual(result["false_negative"], 0)

    def test_recruitment_channel_rule_requires_all_corroboration(self):
        left, right = row(TESCO), row(TECHNOLOGY)
        self.assertTrue(compare(profile(left), profile(right)).matched)
        variants = {}
        modified = copy.deepcopy(right)
        modified["matching_evidence"] = None
        variants["missing_reference"] = modified
        modified = copy.deepcopy(right)
        modified["matching_evidence"]["reference"] = "209434Technology"
        variants["different_requisition"] = modified
        modified = copy.deepcopy(right)
        modified["matching_evidence"]["issuer"] = "Unrelated Employer"
        variants["unbound_issuer"] = modified
        modified = copy.deepcopy(right)
        modified["description"] = modified["description"].replace("Tesco Stores Limited", "an undisclosed client")
        variants["missing_legal_employer"] = modified
        modified = copy.deepcopy(right)
        modified["title"] = "Senior Software Development Engineer II (Java) - Identity"
        variants["different_seniority"] = modified
        modified = copy.deepcopy(right)
        modified["description"] += "\nThis position owns a different product and hiring team."
        variants["different_role_text"] = modified
        modified = copy.deepcopy(right)
        modified["location"] = "London, England, United Kingdom"
        variants["different_workplace"] = modified
        modified = copy.deepcopy(right)
        modified["location"] = "Remote, United Kingdom"
        variants["broad_remote_scope"] = modified
        modified = copy.deepcopy(right)
        modified["company"] = modified["matching_evidence"]["issuer"] = "Tesco Group"
        variants["unverified_brand"] = modified
        for name, modified in variants.items():
            with self.subTest(variant=name):
                self.assertFalse(compare(profile(left), profile(modified)).matched)

    def test_matching_metadata_is_not_content(self):
        raw = row(TESCO)
        before = Listing.from_dict(raw)
        raw["matching_evidence"]["reference"] = "209434TescoUK"
        after = Listing.from_dict(raw)
        self.assertEqual(before.content, after.content)
        self.assertEqual(before.content_hash, after.content_hash)


class RealGroupingTests(unittest.TestCase):
    def setUp(self):
        self.connection = self.enterContext(isolated_database())

    def apply(self, records, minute):
        return reconcile(self.connection, Observation.from_dict({
            "source": "linkedin", "observed_at": CLOCK + timedelta(minutes=minute), "details": records}))

    def seed_without_references(self):
        left, right = row(TESCO), row(TECHNOLOGY)
        left["matching_evidence"] = right["matching_evidence"] = None
        self.apply([left], 0)
        self.apply([right], 1)
        return stored_rows(self.connection)

    def test_metadata_only_merge_preserves_oldest_identity_and_hashes(self):
        before = self.seed_without_references()
        self.assertNotEqual(before[TESCO]["canonical_job_id"], before[TECHNOLOGY]["canonical_job_id"])
        counts = self.apply([row(TESCO), row(TECHNOLOGY)], 2)
        after = stored_rows(self.connection)
        self.assertEqual(counts, {"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
        self.assertEqual(after[TECHNOLOGY]["canonical_job_id"], before[TESCO]["canonical_job_id"])
        for identity in (TESCO, TECHNOLOGY):
            self.assertEqual(after[identity]["first_seen_at"], before[identity]["first_seen_at"])
            self.assertEqual(after[identity]["content_hash"], before[identity]["content_hash"])
        self.assertEqual(self.apply([row(TESCO), row(TECHNOLOGY)], 2), counts)
        self.assertEqual(stored_rows(self.connection), after)

    def test_metadata_change_invalidates_cache_and_splits_conflicting_row(self):
        self.apply([row(TESCO)], 0)
        self.apply([row(TECHNOLOGY)], 1)
        before = stored_rows(self.connection)
        modified = row(TECHNOLOGY)
        modified["matching_evidence"]["reference"] = "209434Technology"
        counts = self.apply([modified], 2)
        after = stored_rows(self.connection)
        self.assertEqual(counts["jobs_changed"], 0)
        self.assertEqual(after[TESCO], before[TESCO])
        self.assertEqual(after[TECHNOLOGY]["content_hash"], before[TECHNOLOGY]["content_hash"])
        self.assertNotEqual(after[TESCO]["canonical_job_id"], after[TECHNOLOGY]["canonical_job_id"])

    def test_missing_metadata_on_wording_edit_retains_established_identity(self):
        self.apply([row(TESCO)], 0)
        self.apply([row(TECHNOLOGY)], 1)
        old_group = stored_rows(self.connection)[TESCO]["canonical_job_id"]
        modified = row(TECHNOLOGY)
        modified["description"] += "\nAdditional guidance on the application process."
        modified["matching_evidence"] = None
        self.assertEqual(self.apply([modified], 2)["jobs_changed"], 1)
        self.assertEqual(stored_rows(self.connection)[TECHNOLOGY]["canonical_job_id"], old_group)
        features = self.connection.execute("SELECT profile FROM dedupe_features WHERE job_id = %s", (TECHNOLOGY,)).fetchone()["profile"]
        self.assertIsNone(features["source_reference_key"])

    def test_delayed_metadata_cannot_overwrite_newer_reference(self):
        self.apply([row(TESCO)], 0)
        changed = row(TESCO)
        changed["matching_evidence"]["reference"] = "209434TescoUK"
        self.apply([changed], 2)
        self.apply([row(TESCO)], 1)
        evidence = self.connection.execute("SELECT reference FROM listing_match_evidence WHERE job_id = %s", (TESCO,)).fetchone()
        self.assertEqual(evidence["reference"], "209434TescoUK")

    def test_evidence_and_canonical_changes_roll_back_with_observation(self):
        before = self.seed_without_references()
        with patch("crawler.reconcile.deduplicate_listing", side_effect=RuntimeError("interrupted grouping")):
            with self.assertRaises(RuntimeError):
                self.apply([row(TESCO), row(TECHNOLOGY)], 2)
        self.assertEqual(stored_rows(self.connection), before)
        self.assertEqual(self.connection.execute("SELECT count(*) AS count FROM listing_match_evidence").fetchone()["count"], 0)


if __name__ == "__main__":
    unittest.main()
