import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crawler.fetching import CrawlBudgetExceeded, Fetcher


URL = "https://www.reed.co.uk/jobs/software-engineer-jobs"


def response(status, text="<html>Job board</html>", headers=None):
    return SimpleNamespace(status_code=status, text=text, content=text.encode(), headers=headers or {})


class FetchingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict("os.environ", {}, clear=True))
        self.enterContext(patch("crawler.fetching.time.sleep"))
        self.session = self.enterContext(patch("crawler.fetching.requests.Session")).return_value
        self.fetcher = Fetcher(self.folder, delay=0)
        self.addCleanup(self.fetcher.close)

    def test_transient_retries_are_bounded_and_every_attempt_is_logged(self):
        self.session.get.side_effect = [response(503), response(502), response(200)]
        result = self.fetcher.fetch("reed", "discovery", URL)
        self.assertTrue(result.usable)
        records = [json.loads(line) for line in (self.folder / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([row["status"] for row in records], [503, 502, 200])
        self.assertEqual(self.fetcher.statistics()["requests_total"], 3)

    def test_persistent_transient_failure_stops_after_three_attempts(self):
        self.session.get.return_value = response(503)
        self.assertFalse(self.fetcher.fetch("reed", "detail", URL).usable)
        self.assertEqual(self.session.get.call_count, 3)

    def test_challenge_is_logged_and_not_retried_as_normal_content(self):
        self.session.get.return_value = response(200, "<title>Additional Verification Required</title>")
        self.assertFalse(self.fetcher.fetch("reed", "detail", URL).usable)
        self.assertEqual(self.fetcher.statistics()["requests_blocked"], 1)
        self.assertEqual(self.session.get.call_count, 1)

    def test_redirects_are_logged_and_off_source_targets_are_not_requested(self):
        self.session.get.side_effect = [response(302, headers={"location": "/jobs/next-page"}), response(200)]
        self.assertTrue(self.fetcher.fetch("reed", "discovery", URL).usable)
        self.assertEqual(len(self.fetcher.records), 2)
        self.session.get.return_value = response(302, headers={"location": "https://example.com/jobs"})
        self.session.get.side_effect = None
        result = self.fetcher.fetch("reed", "discovery", URL)
        self.assertEqual(result.error_type, "UnsafeSourceRedirect")
        self.assertEqual(len(self.fetcher.records), 3)

    def test_request_budget_prevents_extra_network_requests(self):
        self.fetcher.max_requests = 1
        self.session.get.return_value = response(200)
        self.fetcher.fetch("reed", "discovery", URL)
        with self.assertRaises(CrawlBudgetExceeded):
            self.fetcher.fetch("reed", "detail", URL)
        self.assertEqual(self.session.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
