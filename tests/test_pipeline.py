import json
import tempfile
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from crawler.exporting import export_run
from crawler.fetching import FetchResult
from crawler.run import crawl_source
from crawler.reconcile import stored_rows
from tests.support import isolated_database
from tests.test_parsers import CLOCK, FIXTURES, REED


class FakeFetcher:
    def __init__(self, responses):
        self.responses = list(responses)
        self.blocked_by_source = Counter()
        self.calls = []

    def fetch(self, source, kind, url):
        self.calls.append((source, kind, url))
        if not self.responses:
            raise AssertionError("Unnecessary detail request")
        result = self.responses.pop(0)
        if result.blocked_reason:
            self.blocked_by_source[source] += 1
        return result


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.connection = self.enterContext(isolated_database())
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.clock_patch = self.enterContext(patch("crawler.run.now", return_value=CLOCK))
        self.page = (FIXTURES / "reed-detail.html").read_text()
        self.discovery = FetchResult("https://www.reed.co.uk/jobs/software-engineer-jobs", 200, f'<a href="{REED}">Job</a>')
        self.detail = FetchResult(REED, 200, self.page)
        self.counts = Counter()
        self.limits = {"pages": 1, "details": 2, "refresh_hours": 24}

    def crawl(self, fetcher):
        return crawl_source(self.connection, fetcher, self.folder, "reed", ["software engineer"], self.limits, self.counts)

    def test_live_adapter_persists_and_next_run_skips_fresh_details(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        first = stored_rows(self.connection)
        self.assertEqual(self.counts["jobs_new"], 1)
        self.clock_patch.return_value = CLOCK + timedelta(hours=1)
        self.counts.clear()
        fetcher = FakeFetcher([self.discovery])
        result = self.crawl(fetcher)
        self.assertEqual(result["details_skipped_fresh"], 1)
        self.assertEqual(len(fetcher.calls), 1)
        row = stored_rows(self.connection)["reed:57336545"]
        self.assertEqual(row["first_seen_at"], first[row["id"]]["first_seen_at"])
        self.assertEqual(row["content_hash"], first[row["id"]]["content_hash"])
        self.assertEqual(row["last_seen_at"], CLOCK + timedelta(hours=1))

    def test_due_absent_job_refreshes_and_finds_description_only_change(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.clock_patch.return_value = CLOCK + timedelta(hours=25)
        self.counts.clear()
        changed = FetchResult(REED, 200, self.page.replace("protects what matters", "has changed requirements"))
        empty_search = FetchResult(self.discovery.url, 200, "<h1>No matching jobs</h1>")
        self.crawl(FakeFetcher([empty_search, changed]))
        self.assertEqual(self.counts["jobs_changed"], 1)
        self.assertIn("changed requirements", stored_rows(self.connection)["reed:57336545"]["description"])

    def test_failed_refresh_remains_due(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.clock_patch.return_value = CLOCK + timedelta(hours=25)
        original = stored_rows(self.connection)["reed:57336545"]["content_hash"]
        self.crawl(FakeFetcher([self.discovery, FetchResult(REED, 503, "Unavailable")]))
        self.assertEqual(stored_rows(self.connection)["reed:57336545"]["content_hash"], original)
        result = self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.assertEqual(result["details_fetched"], 1)

    def test_not_found_requires_confirmation_and_export_keeps_removed_rows(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.clock_patch.return_value = CLOCK + timedelta(hours=25)
        self.counts.clear()
        missing = FetchResult(REED, 404, "Not found")
        self.crawl(FakeFetcher([self.discovery, missing, missing]))
        self.assertEqual(self.counts["jobs_removed"], 1)
        report = dict(self.counts)
        export_run(self.connection, report, self.folder)
        rows = [json.loads(line) for line in (self.folder / "jobs.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["removed_at"])
        self.assertEqual(report["jobs_by_source"]["reed"], 0)
        self.assertEqual(set(rows[0]), set(stored_rows(self.connection)["reed:57336545"]))

    def test_blocking_and_single_not_found_preserve_good_data(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.clock_patch.return_value = CLOCK + timedelta(hours=25)
        self.crawl(FakeFetcher([self.discovery, FetchResult(REED, 404, "Not found"), FetchResult(REED, 403, "Challenge", "http_403")]))
        row = stored_rows(self.connection)["reed:57336545"]
        self.assertIsNone(row["removed_at"])
        result = self.crawl(FakeFetcher([FetchResult(self.discovery.url, 403, "Challenge", "http_403")]))
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(stored_rows(self.connection)["reed:57336545"]["removed_at"])


if __name__ == "__main__":
    unittest.main()
