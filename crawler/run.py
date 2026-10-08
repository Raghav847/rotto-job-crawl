"""Live discovery, periodic detail refresh, shared reconciliation, and exports."""

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from dotenv import load_dotenv

from crawler.database import connect, database_url, initialize
from crawler.dedupe import backfill
from crawler.exporting import export_run, json_value
from crawler.fetching import CrawlBudgetExceeded, Fetcher
from crawler.models import Observation
from crawler.parsers import Candidate, ExtractionError, IneligibleListing, discover, expired_page, parse_detail, source_id
from crawler.reconcile import reconcile


def now():
    return datetime.now(timezone.utc)


def integer_setting(name, default, minimum=1):
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def discovery_url(source, query, page):
    if source == "linkedin":
        return "https://www.linkedin.com/jobs/search/?" + urlencode({
            "keywords": query, "location": "United Kingdom", "start": page * 25,
        })
    if source == "reed":
        from urllib.parse import quote
        slug = quote(query.lower().replace(" ", "-"), safe="-")
        return f"https://www.reed.co.uk/jobs/{slug}-jobs"
    parameters = {"q": query, "l": "United Kingdom"}
    if page:
        parameters["start"] = page * 10
    return "https://uk.indeed.com/jobs?" + urlencode(parameters)


def observe(connection, source, counters, *, discovered=(), details=(), removed=(), failed=()):
    observation = Observation.from_dict({
        "source": source, "scope": "uk-search-and-scheduled-details", "observed_at": now(),
        "discovery_complete": False, "discovered_source_job_ids": list(discovered),
        "details": [listing.content for listing in details],
        "confirmed_removed_source_job_ids": list(removed), "failed_detail_source_job_ids": list(failed),
    })
    result = reconcile(connection, observation)
    counters.update(result)


def known_listings(connection, source, ids):
    if not ids:
        return {}
    rows = connection.execute(
        "SELECT j.*, s.last_detail_refresh_at FROM jobs j LEFT JOIN listing_state s ON s.job_id = j.id "
        "WHERE j.source = %s AND j.source_job_id = ANY(%s)", (source, list(ids)),
    ).fetchall()
    return {row["source_job_id"]: row for row in rows}


def scheduled_details(connection, source, cutoff, limit):
    return connection.execute(
        "SELECT j.*, s.last_detail_refresh_at FROM jobs j LEFT JOIN listing_state s ON s.job_id = j.id "
        "WHERE j.source = %s AND (s.last_detail_refresh_at IS NULL OR s.last_detail_refresh_at <= %s) "
        "AND (j.removed_at IS NULL OR j.removed_at <= %s) "
        "AND NOT EXISTS (SELECT 1 FROM listing_exclusions e WHERE e.source = j.source "
        "AND e.source_job_id = j.source_job_id AND e.checked_at > %s) "
        "ORDER BY COALESCE(s.last_detail_refresh_at, j.first_seen_at), j.id LIMIT %s",
        (source, cutoff, cutoff, cutoff, limit),
    ).fetchall()


def crawl_source(connection, fetcher, folder, source, queries, limits, counters):
    summary = {"status": "complete", "discovered": 0, "details_fetched": 0,
               "details_skipped_fresh": 0, "accepted": 0, "rejected": {}, "failures": 0}
    candidates = {}
    known = {}
    forced = set()
    cutoff = now() - timedelta(hours=limits["refresh_hours"])

    def event(kind, **fields):
        with (folder / "events.jsonl").open("a") as output:
            output.write(json.dumps({"at": now().isoformat(), "source": source, "kind": kind, **fields}) + "\n")

    for query in queries:
        url = discovery_url(source, query, 0)
        seen_pages = set()
        for page in range(limits["pages"]):
            result = fetcher.fetch(source, "discovery", url)
            if not result.usable:
                summary["status"] = "blocked" if result.blocked_reason else "partial"
                summary["failures"] += 1
                event("discovery_failed", status=result.status, blocked_reason=result.blocked_reason, error_type=result.error_type)
                break
            found, next_url = discover(source, result.text, result.url)
            fingerprint = tuple(sorted(candidate.source_job_id for candidate in found))
            if not found or fingerprint in seen_pages:
                summary["status"] = "partial"
                event("empty_or_repeated_discovery", query=query, page=page)
                break
            seen_pages.add(fingerprint)
            page_known = known_listings(connection, source, [candidate.source_job_id for candidate in found])
            for identity, row in page_known.items():
                known.setdefault(identity, row)
                if row["removed_at"] is not None:
                    forced.add(identity)
            observe(connection, source, counters, discovered=[candidate.source_job_id for candidate in found])
            for candidate in found:
                candidates.setdefault(candidate.source_job_id, candidate)
            if source == "reed" and not next_url:
                break
            if page + 1 == limits["pages"]:
                if summary["status"] == "complete":
                    summary["status"] = "limited"
                break
            url = next_url or discovery_url(source, query, page + 1)
        if fetcher.blocked_by_source[source]:
            break
    summary["discovered"] = len(candidates)
    # Refresh stored jobs even if search did not rediscover them. Oldest due jobs get priority.
    due = scheduled_details(connection, source, cutoff, limits["details"])
    tasks = {row["source_job_id"]: Candidate(row["source_job_id"], row["url"]) for row in due}
    for row in due:
        known.setdefault(row["source_job_id"], row)
    excluded = {row["source_job_id"] for row in connection.execute(
        "SELECT source_job_id FROM listing_exclusions WHERE source = %s AND checked_at > %s", (source, cutoff),
    ).fetchall()}
    for identity, candidate in candidates.items():
        if identity in excluded:
            continue
        stored = known.get(identity)
        if not stored or identity in forced or not stored["last_detail_refresh_at"] or stored["last_detail_refresh_at"] <= cutoff:
            tasks.setdefault(identity, candidate)
        else:
            summary["details_skipped_fresh"] += 1
    rejected = Counter()
    for identity, candidate in tasks.items():
        if fetcher.blocked_by_source[source]:
            summary["status"] = "blocked"
            break
        if summary["details_fetched"] >= limits["details"]:
            if summary["status"] == "complete":
                summary["status"] = "limited"
            break
        result = fetcher.fetch(source, "detail", candidate.url)
        summary["details_fetched"] += 1
        if result.status in (404, 410) and not result.blocked_reason and not result.error_type:
            confirmation = fetcher.fetch(source, "removal_confirmation", candidate.url)
            try:
                matches = source_id(source, result.url) == identity and source_id(source, confirmation.url) == identity
            except ExtractionError:
                matches = False
            if confirmation.status in (404, 410) and not confirmation.blocked_reason and not confirmation.error_type and matches:
                observe(connection, source, counters, removed=[identity])
                event("confirmed_not_found", source_job_id=identity)
                continue
            result = confirmation
        if not result.usable:
            observe(connection, source, counters, failed=[identity])
            summary["failures"] += 1
            summary["status"] = "blocked" if result.blocked_reason else "partial"
            event("detail_failed", source_job_id=identity, status=result.status,
                  blocked_reason=result.blocked_reason, error_type=result.error_type)
            continue
        try:
            if source_id(source, result.url) != identity:
                raise ExtractionError("Redirected to a different source listing")
            if expired_page(source, result.text, identity):
                observe(connection, source, counters, removed=[identity])
                event("explicit_expiry", source_job_id=identity)
                continue
            previous = known.get(identity, {}).get("posted_at")
            listing = parse_detail(source, result.text, result.url, now(), previous, result.rendered_metadata)
        except IneligibleListing as exc:
            reason = str(exc)
            rejected[reason] += 1
            connection.execute(
                "INSERT INTO listing_exclusions (source, source_job_id, checked_at, reason) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (source, source_job_id) DO UPDATE SET checked_at = EXCLUDED.checked_at, reason = EXCLUDED.reason",
                (source, identity, now(), reason),
            )
            event("ineligible", source_job_id=identity, reason=reason)
            continue
        except ValueError as exc:
            observe(connection, source, counters, failed=[identity])
            summary["failures"] += 1
            summary["status"] = "partial"
            event("extraction_failed", source_job_id=identity, error_type=type(exc).__name__, reason=str(exc))
            continue
        observe(connection, source, counters, details=[listing])
        connection.execute("DELETE FROM listing_exclusions WHERE source = %s AND source_job_id = %s", (source, identity))
        summary["accepted"] += 1
        event("stored", source_job_id=identity, content_hash=listing.content_hash)
    summary["rejected"] = dict(rejected)
    return summary


def main():
    load_dotenv()
    mode = os.environ.get("CRAWL_MODE", "live")
    if mode == "probe":
        from crawler.probe import main as probe_main
        probe_main()
        return
    if mode != "live":
        raise ValueError("CRAWL_MODE must be live or probe")
    sources = [value.strip() for value in os.environ.get("CRAWL_SOURCES", "linkedin,reed,indeed").split(",")]
    if not sources or len(sources) != len(set(sources)) or set(sources) - {"indeed", "linkedin", "reed"}:
        raise ValueError("CRAWL_SOURCES must contain unique supported sources")
    queries = [value.strip() for value in os.environ.get("CRAWL_QUERIES", "software engineer").split(",") if value.strip()]
    if not queries:
        raise ValueError("CRAWL_QUERIES cannot be empty")
    limits = {"pages": integer_setting("CRAWL_MAX_PAGES", 1),
              "details": integer_setting("CRAWL_MAX_DETAILS", 10, 0),
              "refresh_hours": integer_setting("DETAIL_REFRESH_HOURS", 24)}
    folder = Path("output/runs") / (now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    fetcher = Fetcher(folder, max_requests=integer_setting("CRAWL_MAX_REQUESTS", 300),
                      max_seconds=integer_setting("CRAWL_MAX_SECONDS", 600),
                      delay=float(os.environ.get("CRAWL_REQUEST_DELAY", "1")),
                      save_pages=os.environ.get("CRAWL_SAVE_PAGES") == "1")
    counters = Counter({"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
    report = {"started_at": now(), "source_runs": {source: {"status": "not_started"} for source in sources},
              "limits": limits, "queries": queries, "status": "finished"}
    exit_code = 0
    try:
        with connect(database_url()) as connection:
            initialize(connection)
            if not connection.execute("SELECT pg_try_advisory_lock(74201932) AS locked").fetchone()["locked"]:
                raise RuntimeError("Another live crawl is already running")
            report["dedupe_rows_indexed"] = backfill(connection)
            try:
                for source in sources:
                    report["source_runs"][source] = {"status": "running"}
                    try:
                        report["source_runs"][source] = crawl_source(connection, fetcher, folder, source, queries, limits, counters)
                    finally:
                        fetcher.finish_source(source)
                    print(f"{source}: {json.dumps(report['source_runs'][source])}")
            except CrawlBudgetExceeded:
                report["status"] = "budget_limited"
                report["source_runs"][source]["status"] = "budget_limited"
            except KeyboardInterrupt:
                report["status"] = "interrupted"
                report["source_runs"][source]["status"] = "interrupted"
                exit_code = 130
            except Exception as exc:
                report["status"] = "failed"
                report["error_type"] = type(exc).__name__
                report["source_runs"][source]["status"] = "failed"
                exit_code = 1
                print(f"Crawl failed: {type(exc).__name__}")
            finally:
                report.update(counters)
                report.update(fetcher.statistics())
                report["finished_at"] = now()
                report["request_log"] = str(folder / "requests.jsonl")
                if report["status"] == "finished" and any(value["status"] != "complete" for value in report["source_runs"].values()):
                    report["status"] = "partial"
                export_run(connection, report)
                (folder / "report.json").write_text(json.dumps(report, default=json_value, indent=2) + "\n")
    finally:
        fetcher.close()
    print(f"Stored live jobs: {report['jobs_by_source']}; lifecycle counts: {dict(counters)}")
    print("Exports: output/jobs.jsonl and output/report.json")
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
