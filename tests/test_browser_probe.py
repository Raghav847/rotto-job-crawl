import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

from playwright.async_api import Error

from crawler.browser_probe import RequestLedger, browser_proxy, experiment


@dataclass(frozen=True)
class FakeRequest:
    url: str
    resource_type: str = "document"


class BrowserLoggingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.ledger = RequestLedger(self.folder)
        self.addCleanup(lambda: self.ledger.stream.close() if not self.ledger.stream.closed else None)

    def test_started_request_is_durable_before_completion(self):
        request = FakeRequest("https://uk.indeed.com/jobs")
        self.ledger.begin(request)
        event = json.loads((self.folder / "events.jsonl").read_text())
        self.assertEqual(event["event"], "started")
        summary = self.ledger.finalize()
        self.assertEqual(summary["requests_total"], 1)
        record = json.loads((self.folder / "requests.jsonl").read_text())
        self.assertEqual(record["error_type"], "Interrupted")

    def test_redirect_events_count_separately_and_statuses_survive_body_failure(self):
        first = FakeRequest("https://uk.indeed.com/")
        second = FakeRequest("https://uk.indeed.com/jobs")
        self.ledger.response(first, 302)
        self.ledger.finish(first)
        self.ledger.response(second, 403)
        self.ledger.finish(second, error_type="ResponseBodyUnavailable")
        summary = self.ledger.finalize()
        self.assertEqual(summary["requests_by_status"], {"302": 1, "403": 1})
        self.assertEqual(summary["requests_blocked"], 1)

    def test_locally_aborted_media_is_not_a_network_request(self):
        request = FakeRequest("https://uk.indeed.com/logo.png", "image")
        self.ledger.begin(request)
        self.ledger.skip(request, "unneeded_media")
        self.ledger.finish(request, error_type="BrowserRequestFailed")
        summary = self.ledger.finalize()
        self.assertEqual(summary["requests_total"], 0)
        self.assertEqual(summary["requests_skipped_locally"], 1)

    def test_challenge_script_does_not_misclassify_as_document_challenge(self):
        request = FakeRequest("https://uk.indeed.com/challenge.js", "script")
        self.ledger.response(request, 200)
        self.ledger.finish(request, body=b"challenge-platform JavaScript")
        summary = self.ledger.finalize()
        self.assertEqual(summary["requests_blocked"], 0)
        self.assertEqual(summary["response_bytes"], 29)

    def test_sticky_parameters_keep_same_proxy_credentials_and_endpoint(self):
        user = "customer-example-cc-GB"
        password = "test password"
        url = f"http://{quote(user)}:{quote(password)}@pr.oxylabs.io:7777"
        original = browser_proxy(url)
        sticky = browser_proxy(url, sticky=True)
        self.assertEqual(original["server"], sticky["server"])
        self.assertEqual(original["password"], sticky["password"])
        self.assertTrue(sticky["username"].startswith(user + "-sessid-"))
        pinned = f"http://{quote(user + '-sessid-existing')}:{quote(password)}@pr.oxylabs.io:7777"
        self.assertEqual(browser_proxy(pinned, sticky=True)["username"], user + "-sessid-existing")


class BrowserStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_failure_still_writes_summary_and_empty_request_log(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch("crawler.browser_probe.async_playwright") as factory:
                factory.return_value.start = AsyncMock(side_effect=Error("Synthetic startup failure"))
                summary = await experiment(folder, None)
            self.assertEqual(summary["error_type"], "Error")
            self.assertEqual(summary["requests_total"], 0)
            self.assertTrue((folder / "summary.json").exists())
            self.assertEqual((folder / "requests.jsonl").read_text(), "")


if __name__ == "__main__":
    unittest.main()
