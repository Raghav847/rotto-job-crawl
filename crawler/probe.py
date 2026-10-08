"""Bounded public-page access diagnostics, not production job exports."""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests
from dotenv import load_dotenv

from crawler.fetching import classify, proxy_url


SOURCES = {
    "indeed": "https://uk.indeed.com/jobs?q=software+engineer&l=United+Kingdom",
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords=software%20engineer&location=United%20Kingdom",
    "reed": "https://www.reed.co.uk/jobs/software-engineer-jobs",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def detail_urls(source, soup, base):
    urls = []
    for tag in soup.select("a[href]"):
        url = urljoin(base, tag["href"])
        candidate = None
        if source == "indeed" and re.search(r"[?&](?:jk|vjk)=[\w-]+", url):
            match = re.search(r"[?&](?:jk|vjk)=([\w-]+)", url)
            candidate = f"https://uk.indeed.com/viewjob?jk={match[1]}"
        if source == "linkedin" and "/jobs/view/" in url:
            candidate = url.split("?")[0].split("#")[0]
        if source == "reed" and re.search(r"/jobs/[^/]+/\d+", url):
            candidate = url.split("?")[0].split("#")[0]
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def page_summary(source, text, base):
    soup = BeautifulSoup(text, "html.parser")
    selectors = {
        "indeed": "#jobDescriptionText",
        "linkedin": ".show-more-less-html__markup",
        "reed": "[itemprop='description'], .job-description, [data-qa='job-description']",
    }
    description = soup.select_one(selectors[source])
    candidates = detail_urls(source, soup, base)
    postings = []

    def collect(value):
        if isinstance(value, list):
            for element in value:
                collect(element)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
                postings.append(value)
            for element in value.values():
                if isinstance(element, (dict, list)):
                    collect(element)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            collect(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
    return {
        "page_title": soup.title.get_text(" ", strip=True) if soup.title else None,
        "candidate_detail_url": candidates[0] if candidates else None,
        "candidate_detail_urls": candidates[:15],
        "description_characters": len(description.get_text("\n", strip=True)) if description else 0,
        "description_preview": description.get_text("\n", strip=True)[:1200] if description else None,
        "jsonld_blocks": len(soup.select("script[type='application/ld+json']")),
        "visible_fields": [{"selector": selector,
                            "elements": [{"text": node.get_text(" ", strip=True)[:200],
                                          "attributes": {key: str(value)[:300] for key, value in node.attrs.items()
                                                         if key in ("src", "alt", "data-qa", "href", "content")}}
                                         for node in soup.select(selector)[:12]]}
                           for selector in (
                               "h1", ".topcard__org-name-link", ".topcard__flavor", ".topcard__flavor--bullet",
                               ".description__job-criteria-item", ".salary", "[itemprop]",
                               "[data-qa]", "img[alt]", "meta[property='og:url']", "link[rel='canonical']",
                           )],
        "jobposting_evidence": [{
            key: posting.get(key) for key in (
                "title", "identifier", "hiringOrganization", "jobLocation",
                "jobLocationType", "applicantLocationRequirements", "datePosted",
                "validThrough", "employmentType", "baseSalary",
            )
        } | {"structured_description_characters": len(BeautifulSoup(
            posting.get("description") or "", "html.parser").get_text("\n", strip=True))}
            for posting in postings],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", type=Path, help="Inspect saved HTML offline, without requests")
    parser.add_argument("--fields", action="store_true", help="Print compact detail-page field evidence")
    args = parser.parse_args()
    if args.inspect:
        for path in sorted(args.inspect.glob("*.html")):
            if args.fields:
                if not path.name.endswith("-detail.html"):
                    continue
                soup = BeautifulSoup(path.read_text(), "html.parser")
                print(path.name)
                for node in soup.select("[data-qa], .topcard__flavor, .description__job-criteria-item, h1, img[data-delayed-url]"):
                    if node.name == "img" and not node.get("alt"):
                        continue
                    print(json.dumps({"qa": node.get("data-qa"), "class": node.get("class"),
                                      "text": node.get_text(" ", strip=True)[:180],
                                      "image_url": node.get("src") or node.get("data-delayed-url")}))
                continue
            source = path.name.split("-")[0]
            print(json.dumps({"source": source, "sample": path.name,
                              **page_summary(source, path.read_text(), SOURCES[source])}))
        return
    load_dotenv()
    if os.environ.get("PROBE_BROWSER") == "1":
        from crawler.browser_probe import main as browser_main
        browser_main()
        return
    proxy = proxy_url()
    sources = os.environ.get("PROBE_SOURCES", ",".join(SOURCES)).split(",")
    if any(source not in SOURCES for source in sources):
        raise ValueError("PROBE_SOURCES must contain indeed, linkedin, and/or reed")
    folder = Path("output/diagnostics") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    summaries = []
    # No automatic redirects or retries: each network call has its own log entry.
    with requests.Session(impersonate="chrome", proxy=proxy) as session:
        def fetch(source, kind, url):
            for redirect in range(4):
                started = time.monotonic()
                entry = {"at": now(), "source": source, "kind": kind, "url": url,
                         "status": None, "blocked_reason": None, "error_type": None,
                         "response_bytes": 0, "redirect_index": redirect}
                response = None
                try:
                    response = session.get(url, timeout=25, allow_redirects=False)
                    entry.update(status=response.status_code,
                                 response_bytes=len(response.content),
                                 blocked_reason=classify(response.status_code, response.text))
                except requests.RequestsError as exc:
                    # Exception text can include proxy credentials; record only its class.
                    entry["error_type"] = type(exc).__name__
                entry["duration_seconds"] = round(time.monotonic() - started, 3)
                records.append(entry)
                with (folder / "requests.jsonl").open("a") as log:
                    log.write(json.dumps(entry) + "\n")
                if response is not None:
                    (folder / f"{source}-{kind}-{redirect}.html").write_text(response.text)
                if response is None or entry["blocked_reason"]:
                    return None
                if response.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(url, response.headers.get("location", ""))
                    if urlsplit(target).hostname != urlsplit(url).hostname:
                        return None
                    url = target
                    continue
                if response.status_code != 200:
                    return None
                (folder / f"{source}-{kind}.html").write_text(response.text)
                return response.text, url
            return None

        for source in sources:
            url = SOURCES[source]
            item = {"source": source, "discovery": None, "detail": None}
            result = fetch(source, "discovery", url)
            if result:
                item["discovery"] = page_summary(source, *result)
                candidates = detail_urls(source, BeautifulSoup(result[0], "html.parser"), result[1])
                index = int(os.environ.get("PROBE_DETAIL_INDEX", "0"))
                candidate = candidates[index] if 0 <= index < len(candidates) else None
                if candidate:
                    time.sleep(2)
                    detail = fetch(source, "detail", candidate)
                    if detail:
                        item["detail"] = page_summary(source, *detail)
            summaries.append(item)
            print(json.dumps(item))
    summary = {
        "mode": "access_diagnostic", "proxy_enabled": bool(proxy),
        "requests_total": len(records),
        "requests_blocked": sum(bool(r["blocked_reason"]) for r in records),
        "response_bytes": sum(r["response_bytes"] for r in records),
        "sources": summaries,
    }
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Diagnostic logs and page samples: {folder}")


if __name__ == "__main__":
    main()
