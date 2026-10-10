import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from crawler.browser_policy import skip_reason
from crawler.browser_transport import IndeedBrowser


@dataclass(frozen=True)
class FakeRequest:
    url: str
    resource_type: str
    redirected_from: object = None


class ResourcePolicyTests(unittest.TestCase):
    def test_observed_repeated_bundles_and_consent_calls_are_skipped(self):
        self.assertEqual(skip_reason("https://c03.s3.indeed.com/shared/remoteEntry.js", "script"), "unneeded_frontend_bundle")
        self.assertEqual(skip_reason("https://d3fw5vlhllyvee.cloudfront.net/one-trust/consent.json", "fetch"), "unneeded_consent_ui")
        self.assertEqual(skip_reason("https://t.indeed.com/signals/gnav/log", "script"), "unneeded_telemetry")
        self.assertIsNone(skip_reason("https://c03.s3.indeed.com/shared/remoteEntry.js", "script", "baseline"))

    def test_security_checks_and_public_documents_remain_available(self):
        for url, kind in (
            ("https://uk.indeed.com/cdn-cgi/challenge-platform/main.js", "script"),
            ("https://challenges.cloudflare.com/turnstile/api.js", "script"),
            ("https://brunhild.challenges.cloudflare.com/verify", "fetch"),
            ("https://t.indeed.com/signals/log?from=cloudflare-static-pages--captcha", "ping"),
            ("https://uk.indeed.com/jobs?q=engineer", "document"),
            ("https://uk.indeed.com/viewjob?jk=abc&spa=1", "xhr"),
        ):
            with self.subTest(url=url):
                self.assertIsNone(skip_reason(url, kind))

    def test_logo_images_are_never_downloaded(self):
        self.assertEqual(skip_reason("https://cdn.example.org/company-logo.png", "image"), "unneeded_media")
        self.assertEqual(skip_reason("https://secure.indeed.com/auth?continue=job", "document"), "account_or_anonymous_auth_gate")


class BudgetReservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_locally_skipped_resources_do_not_consume_request_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = SimpleNamespace(folder=Path(directory), max_requests=1, records=[], deadline=time.monotonic() + 60)
            browser = IndeedBrowser(owner)
            try:
                skipped = FakeRequest("https://c03.s3.indeed.com/shared/remoteEntry.js", "script")
                browser.requested(skipped)
                route = SimpleNamespace(request=skipped, abort=AsyncMock(), continue_=AsyncMock())
                await browser.routed(route)
                self.assertEqual(browser.remaining_requests(), 1)
                self.assertFalse(browser.budget_reached)

                document = FakeRequest("https://uk.indeed.com/jobs", "document")
                browser.requested(document)
                route = SimpleNamespace(request=document, abort=AsyncMock(), continue_=AsyncMock())
                await browser.routed(route)
                route.continue_.assert_awaited_once()
                self.assertEqual(len(browser.ledger.network_entries), 1)

                extra = FakeRequest("https://uk.indeed.com/jobs?vjk=other", "document")
                browser.requested(extra)
                route = SimpleNamespace(request=extra, abort=AsyncMock(), continue_=AsyncMock())
                await browser.routed(route)
                route.abort.assert_awaited_once()
                self.assertEqual(len(browser.ledger.network_entries), 1)
                self.assertTrue(browser.budget_reached)
            finally:
                browser.ledger.finalize()
                browser.runner.close()


if __name__ == "__main__":
    unittest.main()
