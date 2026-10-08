"""Bounded public-page fetching with durable per-attempt request accounting."""

import json
import math
import os
import random
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

from curl_cffi import requests


def proxy_url():
    if os.environ.get("PROXY_URL"):
        return os.environ["PROXY_URL"]
    host = os.environ.get("PROXY_HOST")
    if not host:
        return None
    username, password = os.environ.get("PROXY_USERNAME"), os.environ.get("PROXY_PASSWORD")
    if not username or not password:
        raise ValueError("PROXY_HOST requires PROXY_USERNAME and PROXY_PASSWORD")
    host = host.removeprefix("http://").removeprefix("https://").rstrip("/")
    if ":" not in host:
        host += ":" + os.environ.get("PROXY_PORT", "7777")
    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}"


def classify(status, text):
    if status in (403, 429, 999):
        return f"http_{status}"
    lower = text[:200000].lower()
    for marker in ("verify you are human", "just a moment...", "challenge-platform",
                   "unusual traffic", "security verification", "additional verification required",
                   "enable javascript and cookies to continue"):
        if marker in lower:
            return marker
    return None


class CrawlBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int | None
    text: str
    blocked_reason: str | None = None
    error_type: str | None = None
    rendered_metadata: dict | None = None

    @property
    def usable(self):
        return self.status == 200 and not self.blocked_reason and not self.error_type


class Fetcher:
    def __init__(self, folder: Path, *, max_requests=100, max_seconds=600, delay=1.0, save_pages=False):
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("CRAWL_REQUEST_DELAY must be finite and nonnegative")
        configured_rate = os.environ.get("PROXY_COST_PER_GB_USD")
        self.cost_rate = float(configured_rate) if configured_rate else None
        if self.cost_rate is not None and (not math.isfinite(self.cost_rate) or self.cost_rate < 0):
            raise ValueError("PROXY_COST_PER_GB_USD must be finite and nonnegative")
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.max_requests = max_requests
        self.deadline = time.monotonic() + max_seconds
        self.delay = delay
        self.save_pages = save_pages
        self.records = []
        self.blocked_by_source = Counter()
        self.session = requests.Session(impersonate="chrome", proxy=proxy_url())
        self.last_request_at = None
        self.indeed_browser = None

    def close(self):
        self.finish_source("indeed")
        self.session.close()

    def finish_source(self, source):
        if source == "indeed" and self.indeed_browser:
            self.indeed_browser.close()
            self.indeed_browser = None

    def fetch(self, source, kind, url):
        if source == "indeed" and os.environ.get("INDEED_FETCH_MODE", "browser") == "browser":
            if self.indeed_browser is None:
                from crawler.browser_transport import IndeedBrowser
                self.indeed_browser = IndeedBrowser(self)
            return self.indeed_browser.fetch(kind, url)
        domain = {"indeed": "indeed.com", "linkedin": "linkedin.com", "reed": "reed.co.uk"}[source]
        for redirect in range(4):
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or parsed.username or not (host == domain or host.endswith("." + domain)):
                return FetchResult(url, None, "", error_type="UnsafeSourceRedirect")
            result = None
            for retry in range(3):
                if len(self.records) >= self.max_requests or time.monotonic() >= self.deadline:
                    raise CrawlBudgetExceeded("Configured request/time budget reached")
                if self.last_request_at is not None:
                    time.sleep(max(0, self.delay - (time.monotonic() - self.last_request_at)))
                if time.monotonic() >= self.deadline:
                    raise CrawlBudgetExceeded("Configured time budget reached")
                started = time.monotonic()
                self.last_request_at = started
                record = {
                    "at": datetime.now(timezone.utc).isoformat(), "source": source, "kind": kind,
                    "url": url, "status": None, "blocked_reason": None, "error_type": None,
                    "response_bytes": 0, "retry_index": retry, "redirect_index": redirect,
                }
                response = None
                try:
                    response = self.session.get(url, timeout=min(25, max(1, self.deadline - started)), allow_redirects=False)
                    block = classify(response.status_code, response.text)
                    if any(segment in parsed.path.lower() for segment in ("/authwall", "/checkpoint", "/login")):
                        block = block or "login_wall"
                    record.update(status=response.status_code, blocked_reason=block, response_bytes=len(response.content))
                    result = FetchResult(url, response.status_code, response.text, block)
                except requests.RequestsError as exc:
                    record["error_type"] = type(exc).__name__
                    result = FetchResult(url, None, "", error_type=record["error_type"])
                record["duration_seconds"] = round(time.monotonic() - started, 3)
                self.records.append(record)
                with (self.folder / "requests.jsonl").open("a") as log:
                    log.write(json.dumps(record) + "\n")
                if self.save_pages and response is not None:
                    (self.folder / f"{len(self.records):04d}-{source}-{kind}.html").write_text(response.text)
                if record["blocked_reason"]:
                    self.blocked_by_source[source] += 1
                    return result
                if result.status is None or result.status in (408, 500, 502, 503, 504):
                    if retry < 2:
                        time.sleep(min(2 ** retry + random.uniform(0, 0.5), max(0, self.deadline - time.monotonic())))
                        continue
                break
            if result.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location") if response else None
                if not location:
                    return FetchResult(url, result.status, result.text, error_type="MissingRedirectLocation")
                url = urljoin(url, location)
                continue
            return result
        return FetchResult(url, None, "", error_type="RedirectLimitExceeded")

    def statistics(self):
        statuses = Counter(str(record["status"]) if record["status"] is not None else "error:" + record["error_type"]
                           for record in self.records)
        size = sum(record["response_bytes"] for record in self.records)
        rate = self.cost_rate
        proxied = bool(proxy_url())
        cost = (size / 1_000_000_000 * rate) if rate is not None and proxied else (0.0 if not proxied else None)
        return {
            "requests_total": len(self.records),
            "requests_blocked": sum(bool(record["blocked_reason"]) for record in self.records),
            "requests_by_status": dict(statuses), "response_body_bytes": size,
            "estimated_cost_usd": cost,
            "cost_per_1000_pages_usd": cost / len(self.records) * 1000 if cost is not None and self.records else None,
            "cost_basis": "Decoded response bodies; proxy-billed overhead/compression not measured. Null cost means no USD/GB rate supplied.",
        }
