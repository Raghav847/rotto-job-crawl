"""Cases beyond the public fixture: failures, removal, resumption and atomicity."""

import unittest
from datetime import datetime, timedelta, timezone

from crawler.models import Listing, Observation
from crawler.reconcile import reconcile, stored_rows
from tests.support import isolated_database


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.connection = self.enterContext(isolated_database())
        self.clock = datetime(2026, 4, 2, 8, tzinfo=timezone.utc)

    def observation(self, hour=0, *, discovered=(), details=(), removed=(), failed=(), complete=False, source="reed"):
        return Observation.from_dict({
            "source": source, "scope": "unit-uk", "observed_at": self.clock + timedelta(hours=hour),
            "discovery_complete": complete, "discovered_source_job_ids": list(discovered),
            "details": list(details), "failed_detail_source_job_ids": list(failed),
            "confirmed_removed_source_job_ids": list(removed),
        })

    def listing(self, identity="alpha", **changes):
        return {
            "source": "reed", "source_job_id": identity,
            "url": f"https://www.reed.co.uk/jobs/synthetic/{identity}",
            "title": "Data Engineer", "company": None, "company_logo_url": None,
            "location": "Leeds, England", "work_type": None,
            "salary_min": None, "salary_max": None, "salary_period": None,
            "posted_at": None, "description": "Build and operate reliable data pipelines.", **changes,
        }

    def apply(self, observation):
        return reconcile(self.connection, observation)

    def rows(self):
        return stored_rows(self.connection)

    def test_failure_and_absence_preserve_content_even_with_complete_discovery(self):
        self.apply(self.observation(details=[self.listing()]))
        original = self.rows()["reed:alpha"]
        result = self.apply(self.observation(1, discovered=["alpha", "unknown"], failed=["alpha", "unknown"]))
        self.assertEqual(result, {"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
        row = self.rows()["reed:alpha"]
        self.assertEqual(row["last_seen_at"], self.clock + timedelta(hours=1))
        self.assertEqual(row["content_hash"], original["content_hash"])
        self.assertEqual(set(self.rows()), {"reed:alpha"})
        before = self.rows()
        self.apply(self.observation(2, complete=True))
        self.assertEqual(self.rows(), before)
        state = self.connection.execute("SELECT * FROM listing_state").fetchone()
        self.assertEqual(state["last_detail_refresh_at"], self.clock)

    def test_removal_repeat_and_changed_reappearance(self):
        self.apply(self.observation(details=[self.listing()]))
        original = self.rows()["reed:alpha"]
        self.assertEqual(self.apply(self.observation(1, removed=["alpha", "unknown"]))["jobs_removed"], 1)
        self.assertEqual(self.apply(self.observation(2, removed=["alpha"]))["jobs_removed"], 0)
        self.assertEqual(self.rows()["reed:alpha"]["removed_at"], self.clock + timedelta(hours=1))
        result = self.apply(self.observation(3, details=[self.listing(description="Updated vacancy requirements.")]))
        self.assertEqual(result, {"jobs_new": 0, "jobs_changed": 1, "jobs_removed": 0})
        row = self.rows()["reed:alpha"]
        self.assertIsNone(row["removed_at"])
        self.assertEqual(row["first_seen_at"], self.clock)
        self.assertEqual(row["last_seen_at"], self.clock + timedelta(hours=3))
        self.assertEqual(row["canonical_job_id"], original["canonical_job_id"])
        self.assertNotEqual(row["content_hash"], original["content_hash"])

    def test_discovery_only_reappearance_and_replay(self):
        self.apply(self.observation(details=[self.listing()]))
        self.apply(self.observation(1, removed=["alpha"]))
        observation = self.observation(2, discovered=["alpha"], failed=["alpha"])
        self.apply(observation)
        before = self.rows()
        self.assertIsNone(before["reed:alpha"]["removed_at"])
        self.assertEqual(self.apply(observation), {"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
        self.assertEqual(self.rows(), before)

    def test_description_only_edit_and_numerically_equivalent_salary(self):
        initial = self.listing(salary_min=60000, salary_max=80000, salary_period="year")
        self.apply(self.observation(details=[initial]))
        original_hash = self.rows()["reed:alpha"]["content_hash"]
        self.assertEqual(self.apply(self.observation(1, details=[{**initial, "salary_min": 60000.0}]))["jobs_changed"], 0)
        self.assertEqual(self.rows()["reed:alpha"]["content_hash"], original_hash)
        self.assertEqual(self.apply(self.observation(2, details=[{**initial, "description": "A detail-only edit."}]))["jobs_changed"], 1)

    def test_sources_do_not_collide_and_partial_batches_resume(self):
        first = self.observation(details=[self.listing()])
        self.apply(first)
        linkedin = self.listing(source="linkedin", url="https://www.linkedin.com/jobs/view/alpha")
        self.apply(self.observation(1, source="linkedin", details=[linkedin]))
        self.apply(self.observation(2, details=[self.listing("beta")]))
        self.assertEqual(set(self.rows()), {"reed:alpha", "reed:beta", "linkedin:alpha"})
        self.assertEqual(self.apply(first)["jobs_new"], 0)

    def test_delayed_observations_do_not_undo_newer_state(self):
        self.apply(self.observation(details=[self.listing()]))
        self.apply(self.observation(2, details=[self.listing(title="Updated title")]))
        before = self.rows()
        self.apply(self.observation(1, details=[self.listing()]))
        self.assertEqual(self.rows(), before)
        self.apply(self.observation(3, removed=["alpha"]))
        before = self.rows()
        self.apply(self.observation(2, discovered=["alpha"]))
        self.assertEqual(self.rows(), before)

    def test_transaction_rollback_preserves_previous_batches(self):
        self.apply(self.observation(details=[self.listing()]))
        before = self.rows()
        with self.assertRaises(RuntimeError):
            with self.connection.transaction():
                self.apply(self.observation(1, details=[self.listing("beta")]))
                raise RuntimeError("Simulated interrupted uncommitted batch")
        self.assertEqual(self.rows(), before)

    def test_invalid_or_conflicting_observations_are_rejected_before_writes(self):
        with self.assertRaises(ValueError):
            self.observation(details=[self.listing()], removed=["alpha"])
        with self.assertRaises(ValueError):
            Listing.from_dict(self.listing(description=""))
        self.assertEqual(self.rows(), {})


if __name__ == "__main__":
    unittest.main()
