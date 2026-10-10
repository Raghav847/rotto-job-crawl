import unittest
from datetime import datetime, timedelta, timezone

from crawler.metrics import efficiency


class EfficiencyTests(unittest.TestCase):
    def test_fetch_cost_units_and_unknown_rate_are_explicit(self):
        started = datetime(2026, 10, 9, tzinfo=timezone.utc)
        report = {"started_at": started, "finished_at": started + timedelta(seconds=120),
                  "requests_total": 10, "response_body_bytes": 10_000_000, "jobs_new": 3,
                  "estimated_cost_usd": 0.02, "requests_by_source": {"linkedin": 10},
                  "response_bytes_by_source": {"linkedin": 10_000_000},
                  "source_runs": {"linkedin": {"accepted": 4, "jobs_new": 3, "pages_fetched": 2, "details_fetched": 4}}}
        values = efficiency(report)
        self.assertEqual(values["accepted_per_request"], 0.4)
        self.assertEqual(values["new_per_request"], 0.3)
        self.assertEqual(values["accepted_per_minute"], 2)
        self.assertEqual(values["cost_per_1000_request_attempts_usd"], 2)
        self.assertAlmostEqual(values["cost_per_1000_listing_fetches_usd"], 0.02 * 1000 / 6)
        report["estimated_cost_usd"] = None
        self.assertIsNone(efficiency(report)["cost_per_1000_listing_fetches_usd"])
