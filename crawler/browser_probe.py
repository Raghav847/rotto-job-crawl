"""Bounded Indeed browser access experiment with durable, credential-free logs."""

import asyncio
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from playwright.async_api import Error, async_playwright

from crawler.fetching import Fetcher, classify, proxy_url
from crawler.parsers import discover


RENDERED_METADATA = r"""() => {
    const pane = document.querySelector('[data-testid="viewjob-main-content"]');
    const logo = pane && pane.querySelector('[data-testid="company-logo"]');
    let url = null;
    if (logo) {
        for (const node of [logo, ...logo.querySelectorAll('*')]) {
            const background = getComputedStyle(node).backgroundImage;
            const match = background.match(/url\(["']?(.*?)["']?\)/);
            if (match) { url = match[1]; break; }
            if (node.tagName === 'IMG' && node.src) { url = node.src; break; }
        }
    }
    const ids = new Set();
    if (pane) {
        for (const link of pane.querySelectorAll('a[href]')) {
            const id = new URL(link.href).searchParams.get('fromjk');
            if (id) ids.add(id);
        }
    }
    return {html: document.documentElement.outerHTML, company_logo_url: url,
            logo_present: !!logo, source_job_id: ids.size === 1 ? [...ids][0] : null};
}"""


def now():
    return datetime.now(timezone.utc).isoformat()


def browser_proxy(url, *, sticky=False):
    if not url:
        return None
    parsed = urlsplit(url)
    username = unquote(parsed.username or "")
    if sticky:
        if parsed.hostname != "pr.oxylabs.io":
            raise ValueError("Sticky experiment requires the supplied Oxylabs proxy endpoint")
        if not re.search(r"-sessid(?:_oneip)?-", username):
            username += "-sessid-" + uuid4().hex[:12]
    return {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}",
            "username": username, "password": unquote(parsed.password or "")}


class RequestLedger:
    """Start events survive interrupted experiments; summary counts requests once."""

    def __init__(self, folder):
        self.folder = folder
        self.entries = {}
        self.started = {}
        self.stream = (folder / "events.jsonl").open("a")

    def write(self, request, event):
        self.stream.write(json.dumps({"event": event, **self.entries[request]}) + "\n")
        self.stream.flush()

    def begin(self, request):
        if request in self.entries:
            return
        self.entries[request] = {
            "request_id": len(self.entries) + 1, "at": now(), "source": "indeed",
            "kind": "browser", "url": request.url, "resource_type": request.resource_type,
            "network_attempted": True, "status": None, "error_type": None,
            "blocked_reason": None, "response_bytes": 0, "finished": False,
        }
        self.started[request] = time.monotonic()
        self.write(request, "started")

    def skip(self, request, reason):
        self.begin(request)
        entry = self.entries[request]
        entry.update(network_attempted=False, skip_reason=reason, finished=True,
                     duration_seconds=round(time.monotonic() - self.started[request], 3))
        self.write(request, "skipped_locally")

    def response(self, request, status):
        self.begin(request)
        entry = self.entries[request]
        entry["status"] = status
        entry["blocked_reason"] = classify(status, "")
        self.write(request, "response")

    def finish(self, request, *, body=b"", error_type=None):
        self.begin(request)
        entry = self.entries[request]
        if entry["finished"]:
            return
        entry.update(response_bytes=len(body), error_type=error_type, finished=True,
                     duration_seconds=round(time.monotonic() - self.started[request], 3))
        if request.resource_type == "document":
            entry["blocked_reason"] = classify(entry["status"], body.decode("utf-8", errors="replace"))
        self.write(request, "finished")

    @property
    def network_entries(self):
        return [entry for entry in self.entries.values() if entry["network_attempted"]]

    def finalize(self, extra_records=()):
        for request, entry in self.entries.items():
            if not entry["finished"]:
                self.finish(request, error_type="Interrupted")
        self.stream.close()
        records = self.network_entries + list(extra_records)
        (self.folder / "requests.jsonl").write_text("".join(json.dumps(entry) + "\n" for entry in records))
        statuses = Counter(str(entry["status"]) if entry["status"] is not None else "error:" + str(entry["error_type"])
                           for entry in records)
        return {"requests_total": len(records), "requests_by_status": dict(statuses),
                "requests_blocked": sum(bool(entry["blocked_reason"]) for entry in records),
                "requests_skipped_locally": len(self.entries) - len(self.network_entries),
                "response_bytes": sum(entry["response_bytes"] for entry in records)}


async def experiment(folder, configuration, *, max_requests=40, max_seconds=70, max_bytes=5_000_000,
                     warmup=True, headless=True):
    from crawler.probe import SOURCES, page_summary

    ledger = RequestLedger(folder)
    pages = []
    pending = set()
    context = browser = playwright = None
    stop_reason = None
    error_type = None
    current_kind = "warmup" if warmup else "discovery"
    documents = []
    http_trials = []
    http_records = []

    def spawn(coroutine):
        task = asyncio.create_task(coroutine)
        pending.add(task)
        task.add_done_callback(pending.discard)
        return task

    async def stop(reason):
        nonlocal stop_reason
        if stop_reason:
            return
        stop_reason = reason
        if context:
            try:
                await context.close()
            except Error:
                pass

    def requested(request):
        ledger.begin(request)
        ledger.entries[request]["phase"] = current_kind
        # Request events include redirects even when routing only sees the first hop.
        if len(ledger.network_entries) > max_requests:
            spawn(stop("request_budget"))

    async def routed(route):
        request = route.request
        ledger.begin(request)
        host = urlsplit(request.url).hostname or ""
        if request.resource_type in ("image", "font", "media") or (
            request.resource_type == "stylesheet" and host.endswith(".indeed.com")
        ):
            ledger.skip(request, "unneeded_media")
            await route.abort()
        elif stop_reason or len(ledger.network_entries) > max_requests:
            ledger.skip(request, "request_budget")
            await route.abort()
        else:
            await route.continue_()

    def responded(response):
        ledger.response(response.request, response.status)

    async def finished(request):
        try:
            response = await request.response()
            body = await response.body() if response else b""
            ledger.finish(request, body=body, error_type=None if response else "BrowserRequestFailed")
            host = urlsplit(request.url).hostname or ""
            if request.resource_type == "document" and host.endswith(".indeed.com") and body:
                entry = ledger.entries[request]
                phase = entry.get("phase", current_kind)
                markup = body.decode("utf-8", errors="replace")
                sample = f"indeed-{phase}-response-{entry['request_id']}.html"
                (folder / sample).write_text(markup)
                documents.append({"phase": phase, "url": request.url, "status": entry["status"],
                                  "text": markup, "sample": sample})
        except Error:
            ledger.finish(request, error_type="ResponseBodyUnavailable")
        if sum(entry["response_bytes"] for entry in ledger.network_entries) > max_bytes:
            await stop("response_byte_budget")

    def failed(request):
        ledger.finish(request, error_type="BrowserRequestFailed")

    async def navigate(page, kind, url):
        nonlocal current_kind
        current_kind = kind
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            # Let ordinary page JavaScript run; no CAPTCHA interaction or account use.
            await page.wait_for_timeout(8000)
            # A managed JavaScript check may navigate again after the first response.
            for _ in range(16):
                title = (await page.title()).lower()
                if not any(marker in title for marker in ("just a moment", "security check")):
                    break
                await page.wait_for_timeout(500)
            markup = await page.content()
            metadata = await page.evaluate(RENDERED_METADATA)
            markup = metadata.pop("html")
            (folder / f"indeed-{kind}.html").write_text(markup)
            (folder / f"indeed-{kind}-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
            summary = page_summary("indeed", markup, page.url)
            summary.pop("visible_fields", None)
            latest = next((item for item in reversed(documents) if item["phase"] == kind), None)
            status = latest["status"] if latest else (response.status if response else None)
            summary.update(kind=kind, url=page.url, status=status,
                           rendered_metadata=metadata,
                           challenge_reason=classify(status, markup))
            pages.append(summary)
            return markup if not summary["challenge_reason"] else None
        except Error as exc:
            pages.append({"kind": kind, "error_type": type(exc).__name__})
            return None

    try:
        playwright = await async_playwright().start()
        executable = os.environ.get("BROWSER_EXECUTABLE")
        browser = await playwright.chromium.launch(
            headless=headless, proxy=configuration,
            **({"channel": os.environ["BROWSER_CHANNEL"]} if os.environ.get("BROWSER_CHANNEL") else {}),
            **({"args": ["--disable-blink-features=AutomationControlled"],
                "ignore_default_args": ["--enable-automation"]}
               if os.environ.get("BROWSER_AUTOMATION_COMPAT") == "1" else {}),
            **({"executable_path": executable} if executable else {}),
        )
        options = {"locale": "en-GB", "service_workers": "block"}
        if os.environ.get("BROWSER_STANDARD_UA") == "1":
            inspection_context = await browser.new_context()
            inspection_page = await inspection_context.new_page()
            native_agent = await inspection_page.evaluate("navigator.userAgent")
            options["user_agent"] = native_agent.replace("HeadlessChrome/", "Chrome/")
            await inspection_context.close()
        context = await browser.new_context(**options)
        context.on("request", requested)
        context.on("response", responded)
        context.on("requestfinished", lambda request: spawn(finished(request)))
        context.on("requestfailed", failed)
        await context.route("**/*", routed)
        page = await context.new_page()

        async def visit():
            if warmup:
                await navigate(page, "warmup", "https://uk.indeed.com/")
            if stop_reason:
                return
            markup = await navigate(page, "discovery", SOURCES["indeed"])
            if markup and not stop_reason:
                candidates, _ = discover("indeed", markup, page.url)
                if candidates:
                    if os.environ.get("BROWSER_DETAIL_MODE") in ("http_inline", "browser_inline"):
                        cookies = await context.cookies()
                        user_agent = await page.evaluate("navigator.userAgent")
                        index = min(1, len(candidates) - 1)
                        candidate = candidates[index]
                        parsed = urlsplit(page.url)
                        parameters = dict(parse_qsl(parsed.query))
                        parameters["vjk"] = candidate.source_job_id
                        target = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(parameters), ""))
                        if os.environ.get("BROWSER_DETAIL_MODE") == "browser_inline":
                            await navigate(page, "detail", target)
                            return

                        def http_trial():
                            client = Fetcher(folder / "http", max_requests=3, max_seconds=30, delay=0, save_pages=True)
                            server = urlsplit(configuration["server"]) if configuration else None
                            pinned = None
                            if server:
                                pinned = f"{server.scheme}://{quote(configuration['username'], safe='')}:{quote(configuration['password'], safe='')}@{server.netloc}"
                            client.session.close()
                            from curl_cffi import requests
                            client.session = requests.Session(impersonate="chrome", proxy=pinned)
                            client.session.headers.update({"User-Agent": user_agent, "Referer": page.url, "Accept-Language": "en-GB,en;q=0.9"})
                            for cookie in cookies:
                                client.session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
                            try:
                                result = client.fetch("indeed", "inline_detail", target)
                                item = page_summary("indeed", result.text, result.url)
                                item.pop("visible_fields", None)
                                item.update(status=result.status, url=result.url, target_source_job_id=candidate.source_job_id,
                                            blocked_reason=result.blocked_reason, error_type=result.error_type)
                                return item, client.records
                            finally:
                                client.close()

                        item, records = await asyncio.to_thread(http_trial)
                        http_trials.append(item)
                        http_records.extend(records)
                    else:
                        await navigate(page, "detail", candidates[0].url)

        try:
            await asyncio.wait_for(visit(), timeout=max_seconds)
        except TimeoutError:
            await stop("time_budget")
    except (Error, OSError) as exc:
        error_type = type(exc).__name__
    finally:
        for resource, method in ((context, "close"), (browser, "close"), (playwright, "stop")):
            if resource:
                try:
                    await getattr(resource, method)()
                except (Error, OSError) as exc:
                    error_type = error_type or type(exc).__name__
        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)
        # Preserve HTML evidence even if the renderer was closed by a resource limit.
        document_summaries = []
        for document in documents:
            item = page_summary("indeed", document["text"], document["url"])
            item.pop("visible_fields", None)
            document_summaries.append({key: value for key, value in document.items() if key != "text"} | item)
        summary = {"mode": "browser_access_diagnostic", "proxy_enabled": bool(configuration),
                   "headless": headless, "warmup": warmup, "stop_reason": stop_reason,
                   "standard_user_agent": os.environ.get("BROWSER_STANDARD_UA") == "1",
                   "automation_compat": os.environ.get("BROWSER_AUTOMATION_COMPAT") == "1",
                   "error_type": error_type, "pages": pages, "documents": document_summaries,
                   "http_trials": http_trials, **ledger.finalize(http_records)}
        (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    root = Path(os.environ.get("BROWSER_LOG_ROOT", "output/diagnostics")).resolve()
    folder = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-browser-" + uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=True)
    sticky = os.environ.get("BROWSER_STICKY") == "1"
    configuration = browser_proxy(proxy_url(), sticky=sticky)
    summary = asyncio.run(experiment(
        folder, configuration, max_requests=int(os.environ.get("BROWSER_MAX_REQUESTS", "40")),
        max_seconds=int(os.environ.get("BROWSER_MAX_SECONDS", "70")),
        max_bytes=int(os.environ.get("BROWSER_MAX_BYTES", "5000000")),
        warmup=os.environ.get("BROWSER_WARMUP", "1") == "1",
        headless=os.environ.get("BROWSER_HEADLESS", "1") == "1",
    ))
    summary["sticky_requested"] = sticky
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    print(f"Diagnostic logs and page samples: {folder}")
