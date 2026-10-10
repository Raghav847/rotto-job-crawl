import unittest
from datetime import datetime, timezone
import json

from crawler.parsers import discover
from crawler.run import discovery_url


class DiscoveryTests(unittest.TestCase):
    def test_indeed_next_link_preserves_source_query_parameters(self):
        markup = '<a data-jk="abc123" href="/pagead/clk?ad=opaque">Job</a><a aria-label="Next page" href="/jobs?q=engineer&amp;l=London&amp;radius=25&amp;start=10">Next</a>'
        candidates, next_url = discover("indeed", markup, "https://uk.indeed.com/jobs?q=engineer&l=London")
        self.assertEqual(candidates[0].source_job_id, "abc123")
        self.assertEqual(next_url, "https://uk.indeed.com/jobs?q=engineer&l=London&radius=25&start=10")

    def test_off_source_and_auth_links_are_not_pagination(self):
        for href in ("https://example.com/jobs?pageno=2", "https://www.reed.co.uk/auth/login", "javascript:alert(1)"):
            with self.subTest(href=href):
                markup = f'<link rel="next" href="{href}"><a href="/jobs/engineer/1234">Job</a>'
                self.assertIsNone(discover("reed", markup, "https://www.reed.co.uk/jobs/engineer-jobs")[1])

    def test_guest_offset_advances_by_observed_full_page_size(self):
        self.assertEqual(discovery_url("linkedin", "data engineer", 1, "London", 60),
                         "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=data+engineer&location=London&start=60")

    def test_queries_and_locations_are_encoded(self):
        self.assertIn("q=C%23+engineer", discovery_url("indeed", "C# engineer", 0, "Manchester"))
        self.assertIn("l=Manchester", discovery_url("indeed", "C# engineer", 0, "Manchester"))
        self.assertNotIn("start=0", discovery_url("indeed", "engineer", 0))
        self.assertEqual(discovery_url("reed", "data engineer", 0, "London"),
                         "https://www.reed.co.uk/jobs/data-engineer-jobs-in-london")

    def test_indeed_discovery_dates_are_bound_to_card_ids(self):
        data = {"metaData": {"mosaicProviderJobCardsModel": {"results": [
            {"jobkey": "dated123", "pubDate": 1790899200000},
            {"jobkey": "bad456", "pubDate": 1e100}]}}}
        markup = '<a data-jk="dated123">Job</a><a data-jk="missing789">Other</a><a data-jk="bad456">Bad</a>'
        markup += '<script>window.mosaic.providerData["mosaic-provider-jobcards"] = ' + json.dumps(data) + ';</script>'
        rows, _ = discover("indeed", markup, "https://uk.indeed.com/jobs")
        self.assertEqual(rows[0].posted_at, datetime(2026, 10, 2, tzinfo=timezone.utc))
        self.assertIsNone(rows[1].posted_at)
        self.assertIsNone(rows[2].posted_at)

    def test_hidden_preview_ids_not_in_result_metadata_are_skipped(self):
        data = {"metaData": {"mosaicProviderJobCardsModel": {"results": [{"jobkey": "real123"}]}}}
        markup = '<div aria-hidden="true"><a data-jk="real123">Known real result</a><a data-jk="preview456" href="/viewjob?jk=preview456">Preview</a></div><a data-jk="visible789">Visible fallback</a>'
        markup += '<script>window.mosaic.providerData["mosaic-provider-jobcards"] = ' + json.dumps(data) + ';</script>'
        rejected, verified = set(), set()
        rows, _ = discover("indeed", markup, "https://uk.indeed.com/jobs", rejected_ids=rejected, verified_ids=verified)
        self.assertEqual({item.source_job_id for item in rows}, {"real123", "visible789"})
        self.assertEqual(rejected, {"preview456"})
        self.assertEqual(verified, {"real123"})

    def test_missing_result_metadata_does_not_invent_artefact_evidence(self):
        rejected = set()
        rows, _ = discover("indeed", '<div aria-hidden="true"><a data-jk="real123">Result</a></div>',
                           "https://uk.indeed.com/jobs", rejected_ids=rejected)
        self.assertEqual(rows[0].source_job_id, "real123")
        self.assertEqual(rejected, set())


if __name__ == "__main__":
    unittest.main()
