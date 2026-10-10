import tempfile
import json
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from crawler.fetching import CrawlBudgetExceeded, FetchResult
from crawler.parsers import Candidate
from crawler.progress import (begin_cycle, checkpoint_url, clear_verified_artefacts, pending_count,
                              pending_tasks, queue_candidates, suppress_artefacts)
from crawler.reconcile import stored_rows
from crawler.run import crawl_source
from tests.support import isolated_database
from tests.test_parsers import CLOCK, FIXTURES, REED
from tests.test_pipeline import FakeFetcher


class InterruptingFetcher(FakeFetcher):
    def fetch(self, source, kind, url):
        if self.responses and isinstance(self.responses[0], BaseException):
            self.calls.append((source, kind, url))
            raise self.responses.pop(0)
        return super().fetch(source, kind, url)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = self.enterContext(isolated_database())
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.clock = self.enterContext(patch("crawler.run.now", return_value=CLOCK))
        self.counts = Counter()
        self.limits = {"pages": 3, "details": 0, "refresh_hours": 24}
        self.url = "https://www.reed.co.uk/jobs/software-engineer-jobs"
        self.discovery = FetchResult(self.url, 200, f'<a href="{REED}">Job</a>')
        self.page_one = FetchResult(self.url, 200, self.discovery.text + '<link rel="next" href="/jobs/software-engineer-jobs?pageno=2&amp;sid=ephemeral">')
        self.detail = FetchResult(REED, 200, (FIXTURES / "reed-detail.html").read_text())

    def crawl(self, responses, queries=("software engineer",), summary=None):
        fetcher = InterruptingFetcher(responses)
        result = crawl_source(self.connection, fetcher, self.folder, "reed", queries, self.limits, self.counts, summary=summary)
        return result, fetcher

    def test_committed_page_resumes_after_budget_stop_without_repeating_it(self):
        summary = {}
        with self.assertRaises(CrawlBudgetExceeded):
            self.crawl([self.page_one, CrawlBudgetExceeded()], summary=summary)
        self.assertEqual(summary["discovered"], 1)
        self.assertEqual(summary["pending_details_remaining"], 1)
        self.assertEqual(stored_rows(self.connection), {})
        page_two = FetchResult(self.url + "?pageno=2", 200, f'<a href="{REED.replace("57336545", "57336546")}">Other</a>')
        result, fetcher = self.crawl([page_two])
        self.assertTrue(result["resumed_cycle"])
        self.assertEqual(len(fetcher.calls), 1)
        self.assertEqual(fetcher.calls[0][2], self.url + "?pageno=2")
        self.assertEqual(result["query_runs"][0]["pages_previously_fetched"], 1)
        self.assertEqual(result["query_runs"][0]["unique_ids"], 2)
        self.assertEqual(pending_count(self.connection, "reed"), 2)

    def test_interrupt_after_discovery_resumes_details_and_skips_completed_scopes(self):
        self.limits["details"] = 1
        with self.assertRaises(KeyboardInterrupt):
            self.crawl([self.discovery, KeyboardInterrupt()])
        self.assertEqual(pending_count(self.connection, "reed"), 1)
        result, fetcher = self.crawl([self.detail])
        self.assertEqual([call[1] for call in fetcher.calls], ["detail"])
        self.assertTrue(result["resumed_cycle"])
        self.assertEqual(result["pages_fetched"], 0)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(pending_count(self.connection, "reed"), 0)
        self.assertEqual(self.counts["jobs_new"], 1)

    def test_completed_details_stay_acknowledged_when_later_detail_is_interrupted(self):
        self.limits["details"] = 2
        discovery = FetchResult(self.url, 200, self.discovery.text + f'<a href="{REED.replace("57336545", "57336546")}">Other</a>')
        with self.assertRaises(KeyboardInterrupt):
            self.crawl([discovery, self.detail, KeyboardInterrupt()])
        first = stored_rows(self.connection)["reed:57336545"]
        self.counts.clear()
        other = FetchResult(REED.replace("57336545", "57336546"), 200, self.detail.text.replace("57336545", "57336546"))
        result, fetcher = self.crawl([other])
        self.assertEqual(fetcher.calls[0][2], other.url)
        self.assertEqual(stored_rows(self.connection)["reed:57336545"], first)
        self.assertEqual(result["details_fetched"], 1)
        self.assertEqual(self.counts["jobs_new"], 1)

    def test_pending_work_survives_changed_scopes_and_is_not_a_new_sighting(self):
        self.limits["details"] = 1
        self.crawl([self.discovery, self.detail])
        before = stored_rows(self.connection)["reed:57336545"]
        queue_candidates(self.connection, "reed", [Candidate("57336545", REED)], CLOCK, forced=["57336545"])
        self.clock.return_value = CLOCK + timedelta(hours=1)
        empty = FetchResult(self.url, 200, "No matching jobs")
        result, _ = self.crawl([empty, FetchResult(REED, 503, "Unavailable")], queries=("different query",))
        self.assertEqual(result["pending_details_loaded"], 1)
        self.assertEqual(stored_rows(self.connection)["reed:57336545"], before)
        self.assertEqual(pending_count(self.connection, "reed"), 1)

    def test_page_queue_and_sighting_roll_back_if_checkpoint_write_fails(self):
        self.limits["details"] = 1
        self.crawl([self.discovery, self.detail])
        before = stored_rows(self.connection)
        self.clock.return_value = CLOCK + timedelta(hours=1)
        with patch("crawler.run.save_checkpoint", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                self.crawl([self.discovery])
        self.assertEqual(stored_rows(self.connection), before)
        self.assertEqual(pending_count(self.connection, "reed"), 0)

    def test_detail_and_acknowledgement_roll_back_together(self):
        self.limits["details"] = 1
        with patch("crawler.run.acknowledge", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                self.crawl([self.discovery, self.detail])
        self.assertEqual(stored_rows(self.connection), {})
        self.assertEqual(pending_count(self.connection, "reed"), 1)
        self.assertEqual(self.counts["jobs_new"], 0)
        result, fetcher = self.crawl([self.detail])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(fetcher.calls[0][1], "detail")

    def test_source_dates_survive_queueing_and_absence_from_later_search(self):
        published = CLOCK - timedelta(days=6)
        url = "https://uk.indeed.com/viewjob?jk=selected456"
        queue_candidates(self.connection, "indeed", [Candidate("selected456", url, published)], CLOCK)
        markup = (FIXTURES / "indeed-detail.html").read_text()
        # Remove date evidence from the current pane's matching metadata card.
        markup = markup.replace('"pubDate":1790899200000', '"pubDate":null')
        result = crawl_source(self.connection, InterruptingFetcher([
            FetchResult("https://uk.indeed.com/jobs", 200, "No matching jobs"),
            FetchResult("https://uk.indeed.com/jobs?vjk=selected456", 200, markup)]),
            self.folder, "indeed", ["different query"], {**self.limits, "details": 1}, self.counts)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(stored_rows(self.connection)["indeed:selected456"]["posted_at"], published)

    def test_stale_or_changed_plan_starts_new_cycle_without_losing_queue(self):
        cycle, _ = begin_cycle(self.connection, "reed", ["engineer"], ["United Kingdom"], 3, CLOCK, 24)
        queue_candidates(self.connection, "reed", [Candidate("57336545", REED)], CLOCK)
        same, resumed = begin_cycle(self.connection, "reed", ["engineer"], ["United Kingdom"], 3, CLOCK + timedelta(hours=1), 24)
        self.assertTrue(resumed)
        self.assertEqual(same["cycle_id"], cycle["cycle_id"])
        fresh, resumed = begin_cycle(self.connection, "reed", ["engineer"], ["United Kingdom"], 3, CLOCK + timedelta(hours=25), 24)
        self.assertFalse(resumed)
        self.assertNotEqual(fresh["cycle_id"], cycle["cycle_id"])
        changed, resumed = begin_cycle(self.connection, "reed", ["developer"], ["United Kingdom"], 3, CLOCK + timedelta(hours=25), 24)
        self.assertFalse(resumed)
        self.assertNotEqual(changed["cycle_id"], fresh["cycle_id"])
        self.assertEqual(pending_count(self.connection, "reed"), 1)

    def test_failed_pending_candidate_rotates_behind_unattempted_work(self):
        old = Candidate("100", "https://www.reed.co.uk/jobs/engineer/100")
        new = Candidate("200", "https://www.reed.co.uk/jobs/engineer/200")
        queue_candidates(self.connection, "reed", [old, new], CLOCK)
        from crawler.progress import attempt_candidate
        attempt_candidate(self.connection, "reed", old.source_job_id, CLOCK + timedelta(hours=1))
        tasks = pending_tasks(self.connection, "reed", CLOCK - timedelta(hours=24), 1)
        self.assertEqual(tasks, [new])

    def test_unprocessed_details_are_reported_as_limited_after_discovery_ends(self):
        result, _ = self.crawl([self.discovery])
        self.assertEqual(result["query_runs"][0]["status"], "no_next_link")
        self.assertEqual(result["pending_details_remaining"], 1)
        self.assertEqual(result["status"], "limited")

    def test_artefact_cleanup_preserves_jobs_and_valid_metadata_can_clear_it(self):
        self.limits["details"] = 1
        self.crawl([self.discovery, self.detail])
        before = stored_rows(self.connection)
        queue_candidates(self.connection, "reed", [Candidate("57336545", REED), Candidate("999", "https://www.reed.co.uk/jobs/engineer/999")], CLOCK,
                         forced=["57336545"])
        with self.connection.transaction():
            self.assertEqual(suppress_artefacts(self.connection, "reed", {"57336545", "999"}, CLOCK), 1)
        self.assertEqual(stored_rows(self.connection), before)
        self.assertEqual(pending_count(self.connection, "reed"), 1)
        exclusion = self.connection.execute("SELECT reason FROM listing_exclusions WHERE source_job_id='999'").fetchone()
        self.assertEqual(exclusion["reason"], "hidden_discovery_artefact")
        clear_verified_artefacts(self.connection, "reed", {"999"})
        self.assertIsNone(self.connection.execute("SELECT 1 FROM listing_exclusions WHERE source_job_id='999'").fetchone())

    def test_auto_queue_drain_skips_discovery_without_fabricating_sightings(self):
        queue_candidates(self.connection, "reed", [Candidate("57336545", REED)], CLOCK)
        self.limits.update(details=1, discovery="auto")
        result, fetcher = self.crawl([self.detail])
        self.assertTrue(result["discovery_skipped"])
        self.assertEqual(result["pages_fetched"], 0)
        self.assertEqual([call[1] for call in fetcher.calls], ["detail"])
        self.assertEqual(result["accepted"], 1)

    def test_auto_discovery_runs_on_empty_queue(self):
        self.limits.update(details=1, discovery="auto")
        result, fetcher = self.crawl([self.discovery, self.detail])
        self.assertFalse(result["discovery_skipped"])
        self.assertEqual([call[1] for call in fetcher.calls], ["discovery", "detail"])

    def test_auto_does_not_discard_an_unfinished_discovery_checkpoint(self):
        self.limits.update(details=1, discovery="auto")
        with self.assertRaises(CrawlBudgetExceeded):
            self.crawl([self.page_one, CrawlBudgetExceeded()])
        empty = FetchResult(self.url + "?pageno=2", 200, "No matching jobs")
        result, fetcher = self.crawl([empty, self.detail])
        self.assertTrue(result["resumed_cycle"])
        self.assertFalse(result["discovery_skipped"])
        self.assertEqual(fetcher.calls[0][2], self.url + "?pageno=2")

    def test_explicit_queue_drain_preserves_an_unfinished_discovery_cycle(self):
        with self.assertRaises(CrawlBudgetExceeded):
            self.crawl([self.page_one, CrawlBudgetExceeded()])
        before = self.connection.execute("SELECT * FROM crawl_progress WHERE source='reed'").fetchone()
        self.limits.update(details=1, discovery="never")
        result, _ = self.crawl([self.detail])
        self.assertTrue(result["discovery_skipped"])
        self.assertEqual(self.connection.execute("SELECT * FROM crawl_progress WHERE source='reed'").fetchone(), before)

    def test_recent_saved_artefact_proof_cleans_queue_without_new_sightings(self):
        run_folder = self.folder / "current"
        run_folder.mkdir()
        saved = self.folder / (CLOCK.strftime("%Y%m%dT%H%M%SZ") + "-saved") / "indeed-browser"
        saved.mkdir(parents=True)
        metadata = {"metaData": {"mosaicProviderJobCardsModel": {"results": [{"jobkey": "real123"}]}}}
        markup = '<a data-jk="real123">Real</a><div aria-hidden="true"><a data-jk="preview456">Preview</a></div>'
        markup += '<script>window.mosaic.providerData["mosaic-provider-jobcards"] = ' + json.dumps(metadata) + ';</script>'
        (saved / "0001-discovery.html").write_text(markup)
        queue_candidates(self.connection, "indeed", [Candidate("real123", "https://uk.indeed.com/viewjob?jk=real123"),
                                                     Candidate("preview456", "https://uk.indeed.com/viewjob?jk=preview456")], CLOCK)
        fetcher = InterruptingFetcher([])
        result = crawl_source(self.connection, fetcher, run_folder, "indeed", ["engineer"],
                              {**self.limits, "discovery": "never"}, self.counts)
        self.assertEqual(result["artefact_queue_entries_suppressed"], 1)
        self.assertEqual(pending_count(self.connection, "indeed"), 1)
        self.assertEqual(stored_rows(self.connection), {})
        self.assertEqual(fetcher.calls, [])


class CheckpointURLTests(unittest.TestCase):
    def test_saved_search_links_strip_sessions_and_preserve_scope(self):
        self.assertEqual(checkpoint_url("reed", "https://www.reed.co.uk/jobs/engineer-jobs-in-london?sid=ephemeral&locationName=london&pageno=2"),
                         "https://www.reed.co.uk/jobs/engineer-jobs-in-london?locationName=london&pageno=2")
        self.assertIn("start=60", checkpoint_url("linkedin", "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=engineer&location=London&start=60&trackingId=ephemeral"))
        dummy_credentials_url = f"https://{'user'}:{'password'}@www.reed.co.uk/jobs"
        for url in ("https://example.com/jobs", dummy_credentials_url, "https://www.reed.co.uk/auth/login"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checkpoint_url("reed", url)


if __name__ == "__main__":
    unittest.main()
