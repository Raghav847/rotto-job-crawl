"""One bounded Indeed browser experiment, with no interactive challenge solving."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Error, sync_playwright

from crawler.probe import SOURCES, classify, now, page_summary, proxy_url


def main():
    proxy = proxy_url()
    configuration = {}
    if proxy:
        parsed = urlsplit(proxy)
        configuration["proxy"] = {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}",
            "username": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
        }
    folder = Path("output/diagnostics") / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-browser")
    folder.mkdir(parents=True, exist_ok=True)
    entries = {}
    skipped = 0
    budget = 30
    outcome = None
    with sync_playwright() as playwright:
        executable = os.environ.get("BROWSER_EXECUTABLE")
        browser = playwright.chromium.launch(
            headless=True, **configuration,
            **({"executable_path": executable} if executable else {}),
        )
        context = browser.new_context(locale="en-GB", service_workers="block")

        def route_request(route):
            nonlocal skipped
            request = route.request
            if request.resource_type in ("image", "font", "media") or len(entries) >= budget:
                skipped += 1
                route.abort()
                return
            entries[request] = {
                "at": now(), "source": "indeed", "kind": "browser_discovery",
                "url": request.url, "resource_type": request.resource_type,
                "status": None, "error_type": None, "blocked_reason": None,
                "response_bytes": 0, "started_monotonic": time.monotonic(),
            }
            route.continue_()

        def finish(request):
            entry = entries.get(request)
            if not entry or "duration_seconds" in entry:
                return
            response = request.response()
            if response:
                entry["status"] = response.status
                try:
                    body = response.body()
                    entry["response_bytes"] = len(body)
                    entry["blocked_reason"] = classify(response.status, body.decode("utf-8", errors="replace"))
                except Error:
                    entry["error_type"] = "ResponseBodyUnavailable"
            else:
                entry["error_type"] = "BrowserRequestFailed"
            entry["duration_seconds"] = round(time.monotonic() - entry["started_monotonic"], 3)

        context.route("**/*", route_request)
        context.on("requestfinished", finish)
        context.on("requestfailed", finish)
        page = context.new_page()
        try:
            page.goto(SOURCES["indeed"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(10000)
            html = page.content()
            (folder / "indeed-browser.html").write_text(html)
            outcome = page_summary("indeed", html, page.url)
            outcome["challenge_reason"] = classify(200, html)
        except Error as exc:
            outcome = {"error_type": type(exc).__name__}
        finally:
            context.close()
            browser.close()
    for entry in entries.values():
        started = entry.pop("started_monotonic")
        if "duration_seconds" not in entry:
            entry.update(error_type="Interrupted", duration_seconds=round(time.monotonic() - started, 3))
    records = list(entries.values())
    (folder / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    summary = {
        "mode": "browser_access_diagnostic", "proxy_enabled": bool(proxy),
        "requests_total": len(records), "requests_blocked": sum(bool(r["blocked_reason"]) for r in records),
        "requests_skipped_locally": skipped,
        "response_bytes": sum(r["response_bytes"] for r in records), "outcome": outcome,
    }
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    print(f"Diagnostic logs and page samples: {folder}")
