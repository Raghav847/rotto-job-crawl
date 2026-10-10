"""Persistent headless Chromium transport for public Indeed job panes."""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error, async_playwright

from crawler.browser_probe import RENDERED_METADATA, RequestLedger, browser_proxy
from crawler.browser_policy import skip_reason
from crawler.fetching import CrawlBudgetExceeded, FetchResult, classify, proxy_url


def network_error(message, fallback="BrowserRequestFailed"):
    match = re.search(r"net::ERR_[A-Z0-9_]+", message or "")
    return match[0] if match else fallback


class IndeedBrowser:
    def __init__(self, owner):
        self.owner = owner
        self.folder = owner.folder / "indeed-browser"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.runner = asyncio.Runner()
        self.ledger = RequestLedger(self.folder)
        self.playwright = self.browser = self.context = self.page = None
        self.pending = set()
        self.current_kind = "discovery"
        self.last_search_url = "https://uk.indeed.com/jobs?q=software+engineer&l=United+Kingdom"
        self.latest_status = None
        self.budget_reached = False
        self.closed = False
        self.warmed = False
        self.policy = os.environ.get("INDEED_RESOURCE_POLICY", "lean")
        if self.policy not in ("lean", "baseline"):
            raise ValueError("INDEED_RESOURCE_POLICY must be lean or baseline")

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    def remaining_requests(self):
        return self.owner.max_requests - len(self.owner.records) - len(self.ledger.network_entries)

    async def stop(self):
        if self.budget_reached:
            return
        self.budget_reached = True
        if self.context:
            try:
                await self.context.close()
            except Error:
                pass

    def requested(self, request):
        redirected = request.redirected_from is not None
        self.ledger.begin(request, network_attempted=redirected)
        self.ledger.entries[request]["kind"] = self.current_kind
        if redirected and self.remaining_requests() < 0:
            self.spawn(self.stop())

    async def routed(self, route):
        request = route.request
        self.ledger.begin(request, network_attempted=False)
        reason = skip_reason(request.url, request.resource_type, self.policy)
        if reason:
            self.ledger.skip(request, reason)
            await route.abort()
        elif self.budget_reached or self.remaining_requests() <= 0 or time.monotonic() >= self.owner.deadline:
            self.ledger.skip(request, "crawl_budget")
            await route.abort()
            self.budget_reached = True
        else:
            self.ledger.dispatch(request)
            await route.continue_()

    def responded(self, response):
        self.ledger.response(response.request, response.status)
        if response.request.resource_type == "document" and response.request.frame == self.page.main_frame:
            self.latest_status = response.status

    async def finished(self, request):
        try:
            response = await request.response()
            body = await response.body() if response else b""
            self.ledger.finish(request, body=body, error_type=None if response else "BrowserRequestFailed")
        except Error:
            self.ledger.finish(request, error_type="ResponseBodyUnavailable")

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=os.environ.get("INDEED_HEADLESS", "1") == "1", channel="chromium",
            proxy=browser_proxy(proxy_url(), sticky=bool(proxy_url())),
            args=["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"],
        )
        # Keep the native platform/version, using the normal Chrome product token.
        inspection = await self.browser.new_context()
        blank = await inspection.new_page()
        agent = await blank.evaluate("navigator.userAgent")
        await inspection.close()
        self.context = await self.browser.new_context(locale="en-GB", timezone_id="Europe/London", service_workers="block",
                                                      user_agent=agent.replace("HeadlessChrome/", "Chrome/"))
        self.page = await self.context.new_page()
        self.context.on("request", self.requested)
        self.context.on("response", self.responded)
        self.context.on("requestfinished", lambda request: self.spawn(self.finished(request)))
        self.context.on("requestfailed", lambda request: self.ledger.finish(request, error_type=network_error(request.failure)))
        await self.context.route("**/*", self.routed)

    def inline_url(self, url):
        from crawler.parsers import source_id
        identity = source_id("indeed", url)
        parsed = urlsplit(self.last_search_url)
        parameters = dict(parse_qsl(parsed.query))
        parameters["vjk"] = identity
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(parameters), ""))

    async def navigate(self, kind, url):
        if self.remaining_requests() <= 0 or time.monotonic() >= self.owner.deadline:
            raise CrawlBudgetExceeded("Configured request/time budget reached")
        if self.page is None:
            await self.start()
        if not self.warmed:
            self.warmed = True
            self.current_kind = "warmup"
            try:
                await self.page.goto("https://uk.indeed.com/", wait_until="domcontentloaded", timeout=20000)
                await self.page.wait_for_timeout(8000)
            except Error:
                pass
        self.current_kind = kind
        target = url if kind == "discovery" else self.inline_url(url)
        self.latest_status = None
        try:
            remaining = max(1, self.owner.deadline - time.monotonic())
            await self.page.goto(target, wait_until="domcontentloaded", timeout=min(25000, remaining * 1000))
            # Ordinary page JS may clear a managed check; never interact with CAPTCHA UI.
            for _ in range(30):
                title = (await self.page.title()).lower()
                if not any(marker in title for marker in ("just a moment", "security check")):
                    break
                if time.monotonic() >= self.owner.deadline:
                    raise CrawlBudgetExceeded("Configured time budget reached")
                await self.page.wait_for_timeout(500)
            await self.page.wait_for_timeout(250 if self.policy == "lean" else 750)
            markup = await self.page.content()
            metadata = await self.page.evaluate(RENDERED_METADATA)
            markup = metadata.pop("html")
            if self.policy == "baseline" and metadata.get("logo_present") and not metadata.get("company_logo_url"):
                await self.page.wait_for_timeout(1500)
                metadata = await self.page.evaluate(RENDERED_METADATA)
                markup = metadata.pop("html")
            block = classify(self.latest_status, markup)
            final = urlsplit(self.page.url)
            if final.hostname == "secure.indeed.com" and final.path.startswith("/auth"):
                block = "logged_out_pagination_or_auth_gate"
            if kind == "discovery" and not block and self.latest_status == 200 and final.hostname == "uk.indeed.com":
                self.last_search_url = self.page.url
            if self.owner.save_pages:
                sample = f"{len(self.ledger.entries):04d}-{kind}"
                (self.folder / (sample + ".html")).write_text(markup)
                (self.folder / (sample + "-metadata.json")).write_text(json.dumps(metadata, indent=2) + "\n")
            if block and block != "logged_out_pagination_or_auth_gate":
                self.owner.blocked_by_source["indeed"] += 1
            error = "InlineEndpointFailure" if kind != "discovery" and self.latest_status in (404, 410) else None
            return FetchResult(self.page.url, self.latest_status, markup, block, error, metadata)
        except Error as exc:
            if self.budget_reached:
                raise CrawlBudgetExceeded("Configured browser request budget reached") from None
            return FetchResult(target, self.latest_status, "", error_type=network_error(str(exc), type(exc).__name__))

    def fetch(self, kind, url):
        try:
            for attempt in range(2):
                result = self.runner.run(self.navigate(kind, url))
                transient = result.error_type in {
                    "net::ERR_TUNNEL_CONNECTION_FAILED", "net::ERR_PROXY_CONNECTION_FAILED",
                    "net::ERR_CONNECTION_RESET", "net::ERR_CONNECTION_CLOSED", "net::ERR_TIMED_OUT",
                }
                if not transient or attempt == 1:
                    return result
                self.runner.run(self.shutdown())
                self.playwright = self.browser = self.context = self.page = None
                self.warmed = False
                time.sleep(1)
        except Error as exc:
            # Startup failures contain launch arguments; report class only, not credentials.
            return FetchResult(url, None, "", error_type=type(exc).__name__)

    async def shutdown(self):
        for resource, method in ((self.context, "close"), (self.browser, "close"), (self.playwright, "stop")):
            if resource:
                try:
                    await getattr(resource, method)()
                except Error:
                    pass
        if self.pending:
            await asyncio.gather(*list(self.pending), return_exceptions=True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.runner.run(self.shutdown())
        finally:
            summary = self.ledger.finalize()
            summary["resource_policy"] = self.policy
            summary["navigation_requests"] = sum(record["resource_type"] == "document" for record in self.ledger.network_entries)
            records = self.ledger.network_entries
            with (self.owner.folder / "requests.jsonl").open("a") as log:
                for record in records:
                    log.write(json.dumps(record) + "\n")
            self.owner.records.extend(records)
            (self.folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            self.runner.close()
