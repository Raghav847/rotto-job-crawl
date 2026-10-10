import json
import tempfile
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup

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
        if result.blocked_reason and result.blocked_reason != "logged_out_pagination_or_auth_gate":
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

    def test_explicit_maintenance_refresh_preserves_first_seen(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        before = stored_rows(self.connection)["reed:57336545"]
        self.clock_patch.return_value = CLOCK + timedelta(hours=1)
        with patch.dict("os.environ", {"CRAWL_FORCE_REFRESH": "1"}):
            result = self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.assertEqual(result["details_fetched"], 1)
        self.assertEqual(stored_rows(self.connection)["reed:57336545"]["first_seen_at"], before["first_seen_at"])

    def test_targeted_maintenance_refreshes_only_requested_fresh_listing(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        other_url = REED.replace("57336545", "57336546")
        discovery = FetchResult(self.discovery.url, 200, f'<a href="{other_url}">Other job</a>')
        other = FetchResult(other_url, 200, self.page.replace("57336545", "57336546"))
        self.crawl(FakeFetcher([discovery, other]))
        first_seen = stored_rows(self.connection)["reed:57336546"]["first_seen_at"]
        self.clock_patch.return_value = CLOCK + timedelta(hours=1)
        self.limits["details"] = 1
        mixed = FetchResult(self.discovery.url, 200, self.discovery.text + discovery.text)
        fetcher = FakeFetcher([mixed, other])
        result = crawl_source(self.connection, fetcher, self.folder, "reed", ["software engineer"], self.limits,
                              self.counts, refresh_ids=["reed:57336546"])
        self.assertEqual([call[2] for call in fetcher.calls if call[1] == "detail"], [other_url])
        self.assertEqual(result["explicit_refresh_ids"], ["reed:57336546"])
        self.assertEqual(result["details_skipped_fresh"], 1)
        self.assertEqual(stored_rows(self.connection)["reed:57336546"]["first_seen_at"], first_seen)

    def test_unknown_targeted_refresh_does_not_fetch_a_listing(self):
        fetcher = FakeFetcher([])
        with self.assertRaisesRegex(ValueError, "existing stored listing"):
            crawl_source(self.connection, fetcher, self.folder, "reed", ["engineer"], self.limits, self.counts,
                         refresh_ids=["reed:99999999"])
        self.assertEqual(fetcher.calls, [])

    def test_repeated_pagination_stops_without_removals(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        page = FetchResult(self.discovery.url, 200, self.discovery.text + '<link rel="next" href="/jobs/software-engineer-jobs?pageno=2">')
        self.limits.update(pages=5, details=0)
        result = self.crawl(FakeFetcher([page, page]))
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(result["query_runs"][0]["status"], "repeated_page")
        self.assertIsNone(stored_rows(self.connection)["reed:57336545"]["removed_at"])

    def test_overlapping_queries_do_not_fetch_details_twice(self):
        fetcher = FakeFetcher([self.discovery, self.discovery, self.detail])
        result = crawl_source(self.connection, fetcher, self.folder, "reed", ["engineer", "developer"], self.limits, self.counts)
        self.assertEqual(result["discovered"], 1)
        self.assertEqual(result["overlapping_sightings"], 1)
        self.assertEqual(result["details_fetched"], 1)

    def test_failed_second_page_keeps_first_page_data(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        page = FetchResult(self.discovery.url, 200, self.discovery.text + '<link rel="next" href="/jobs/software-engineer-jobs?pageno=2">')
        self.limits.update(pages=3, details=0)
        result = self.crawl(FakeFetcher([page, FetchResult(self.discovery.url + "?pageno=2", 503, "Unavailable")]))
        self.assertEqual(result["query_runs"][0]["status"], "failed")
        self.assertEqual(set(stored_rows(self.connection)), {"reed:57336545"})
        self.assertIsNone(stored_rows(self.connection)["reed:57336545"]["removed_at"])

    def test_indeed_signin_limit_allows_other_public_scopes(self):
        url = "https://uk.indeed.com/jobs?q=engineer"
        page = FetchResult(url, 200, '<a data-jk="abc123">Job</a><a aria-label="Next page" href="/jobs?q=engineer&amp;start=10">Next</a>')
        gate = FetchResult("https://secure.indeed.com/auth", 200, "Sign in", "logged_out_pagination_or_auth_gate")
        other = FetchResult(url, 200, page.text.replace("abc123", "def456"))
        fetcher = FakeFetcher([page, gate, other])
        self.limits.update(pages=3, details=0)
        result = crawl_source(self.connection, fetcher, self.folder, "indeed", ["engineer", "developer"], self.limits, self.counts)
        self.assertEqual(result["discovered"], 2)
        self.assertEqual([run["status"] for run in result["query_runs"]], ["signin_limited", "known_signin_page_limit"])
        self.assertEqual(len(fetcher.calls), 3)
        self.assertEqual(self.counts["jobs_removed"], 0)

    def test_linkedin_guest_offsets_follow_distinct_observed_ids(self):
        url = "https://www.linkedin.com/jobs/search/"
        def page(ids):
            return FetchResult(url, 200, "".join(f'<a href="https://www.linkedin.com/jobs/view/{identity}">Job</a>' for identity in ids))
        fetcher = FakeFetcher([page([101, 102, 103]), page([103, 104]), page([104])])
        self.limits.update(pages=3, details=0)
        result = crawl_source(self.connection, fetcher, self.folder, "linkedin", ["engineer"], self.limits, self.counts)
        self.assertEqual(result["discovered"], 4)
        self.assertTrue(fetcher.calls[1][2].endswith("start=3"))
        self.assertTrue(fetcher.calls[2][2].endswith("start=4"))

    def test_missing_indeed_date_is_enriched_only_after_successful_detail(self):
        soup = BeautifulSoup((FIXTURES / "indeed-detail.html").read_text(), "html.parser")
        soup.select_one("#mosaic-data").decompose()
        payload = {"jobKey": "selected456", "jobCountry": "GB", "loggedIn": False,
                   "jobLocation": "Manchester", "datePublished": None,
                   "jobInfoWrapperModel": {"jobInfoModel": {"jobInfoHeaderModel": {
                       "formattedLocation": "Manchester", "companyName": "Example Engineering"}}}}
        script = soup.new_tag("script")
        script.string = "const view=" + json.dumps(payload) + ";"
        soup.head.append(script)
        url = "https://uk.indeed.com/jobs?q=engineer"
        discovery = FetchResult(url, 200, '<a data-jk="selected456">Job</a>')
        detail = FetchResult(url + "&vjk=selected456", 200, str(soup))
        def crawl(responses):
            return crawl_source(self.connection, FakeFetcher(responses), self.folder, "indeed", ["engineer"], self.limits, self.counts)
        crawl([discovery, detail])
        original = stored_rows(self.connection)["indeed:selected456"]
        self.assertIsNone(original["posted_at"])
        data = {"metaData": {"mosaicProviderJobCardsModel": {"results": [
            {"jobkey": "selected456", "pubDate": 1790899200000}]}}}
        dated = FetchResult(url, 200, '<a data-jk="new789">New job first</a>' + discovery.text + '<script>window.mosaic.providerData["mosaic-provider-jobcards"] = ' + json.dumps(data) + ';</script>')
        self.limits["details"] = 1
        self.clock_patch.return_value = CLOCK + timedelta(hours=1)
        crawl([dated, FetchResult(detail.url, 503, "Unavailable")])
        self.assertIsNone(stored_rows(self.connection)["indeed:selected456"]["posted_at"])
        result = crawl([dated, detail])
        row = stored_rows(self.connection)["indeed:selected456"]
        self.assertEqual(result["details_fetched"], 1)
        self.assertEqual(row["posted_at"].isoformat(), "2026-10-02T00:00:00+00:00")
        self.assertEqual(row["first_seen_at"], original["first_seen_at"])
        self.assertEqual(row["canonical_job_id"], original["canonical_job_id"])
        self.assertNotEqual(row["content_hash"], original["content_hash"])

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

    def test_inline_endpoint_error_does_not_authorize_job_removal(self):
        self.crawl(FakeFetcher([self.discovery, self.detail]))
        self.clock_patch.return_value = CLOCK + timedelta(hours=25)
        unknown = FetchResult(REED, 404, "Endpoint unavailable", error_type="InlineEndpointFailure")
        fetcher = FakeFetcher([self.discovery, unknown])
        self.crawl(fetcher)
        self.assertEqual(len(fetcher.calls), 2)
        self.assertIsNone(stored_rows(self.connection)["reed:57336545"]["removed_at"])


if __name__ == "__main__":
    unittest.main()
