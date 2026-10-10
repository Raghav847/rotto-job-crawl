"""Live discovery, periodic detail refresh, shared reconciliation, and exports."""

import json
import hashlib
import os
import re
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
from crawler.metrics import efficiency
from crawler.parsers import Candidate, ExtractionError, IneligibleListing, discover, expired_page, parse_detail, source_id
from crawler.reconcile import reconcile
from crawler.progress import (acknowledge, attempt_candidate, begin_cycle, checkpoint_url,
                              clear_verified_artefacts, load_checkpoint, pending_count, pending_tasks,
                              queue_candidates, save_checkpoint, suppress_artefacts)


def now():
    return datetime.now(timezone.utc)


def integer_setting(name, default, minimum=1):
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def discovery_url(source, query, page, location="United Kingdom", offset=None):
    if source == "linkedin":
        path = "/jobs/search/" if page == 0 else "/jobs-guest/jobs/api/seeMoreJobPostings/search"
        return "https://www.linkedin.com" + path + "?" + urlencode({
            "keywords": query, "location": location, "start": offset if offset is not None else page * 25})
    if source == "reed":
        from urllib.parse import quote
        slug = quote(query.lower().replace(" ", "-"), safe="-")
        suffix = "" if location == "United Kingdom" else "-in-" + quote(location.lower().replace(" ", "-"), safe="-")
        return f"https://www.reed.co.uk/jobs/{slug}-jobs{suffix}"
    parameters = {"q": query, "l": location}
    if page:
        parameters["start"] = page * 10
    return "https://uk.indeed.com/jobs?" + urlencode(parameters)


def observe(connection, source, counters, *, discovered=(), details=(), removed=(), failed=()):
    observation = Observation.from_dict({
        "source": source, "scope": "uk-search-and-scheduled-details", "observed_at": now(),
        "discovery_complete": False, "discovered_source_job_ids": list(discovered),
        "details": [{**listing.content, "matching_evidence": listing.matching_evidence} for listing in details],
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
        "SELECT j.*, s.last_detail_refresh_at, p.posted_at AS discovery_posted_at FROM jobs j LEFT JOIN listing_state s ON s.job_id = j.id "
        "LEFT JOIN pending_candidates p ON p.source = j.source AND p.source_job_id = j.source_job_id "
        "WHERE j.source = %s AND (s.last_detail_refresh_at IS NULL OR s.last_detail_refresh_at <= %s) "
        "AND (j.removed_at IS NULL OR j.removed_at <= %s) "
        "AND NOT EXISTS (SELECT 1 FROM listing_exclusions e WHERE e.source = j.source "
        "AND e.source_job_id = j.source_job_id AND e.checked_at > %s) "
        "ORDER BY COALESCE(s.last_detail_refresh_at, j.first_seen_at), j.id LIMIT %s",
        (source, cutoff, cutoff, cutoff, limit),
    ).fetchall()


def crawl_source(connection, fetcher, folder, source, queries, limits, counters, locations=("United Kingdom",), summary=None, refresh_ids=()):
    if summary is None:
        summary = {}
    counts_before = dict(counters)
    summary.update({"status": "complete", "discovered": 0, "details_fetched": 0,
               "details_skipped_fresh": 0, "accepted": 0, "rejected": {}, "failures": 0,
               "pages_fetched": 0, "overlapping_sightings": 0, "query_runs": [],
               "removal_confirmations": 0,
               "discovery_artefacts_skipped": 0, "artefact_queue_entries_suppressed": 0,
               "pending_details_loaded": 0, "pending_details_remaining": pending_count(connection, source)})
    try:
        return _crawl_source(connection, fetcher, folder, source, queries, limits, counters, locations, summary, refresh_ids)
    finally:
        for key in ("jobs_new", "jobs_changed", "jobs_removed"):
            summary[key] = counters[key] - counts_before.get(key, 0)
        summary["pending_details_remaining"] = pending_count(connection, source)
        if summary["status"] == "complete" and summary["pending_details_remaining"]:
            summary["status"] = "limited"


def _crawl_source(connection, fetcher, folder, source, queries, limits, counters, locations, summary, refresh_ids):
    candidates = {}
    known = {}
    cutoff = now() - timedelta(hours=limits["refresh_hours"])
    if os.environ.get("CRAWL_FORCE_REFRESH") == "1":
        cutoff = now()
    target_ids = [identity.split(":", 1)[1] for identity in refresh_ids if identity.startswith(source + ":")]
    targets = known_listings(connection, source, target_ids)
    if set(target_ids) - targets.keys():
        raise ValueError("Explicit detail refresh requires an existing stored listing")
    summary["explicit_refresh_ids"] = [source + ":" + identity for identity in targets]
    if source == "indeed" and pending_count(connection, source):
        # Reuse recent saved source proof to clean pre-fix pending UI previews.
        # This is not a new observation and never changes a stored job's lifecycle.
        rejected = set()
        evidence_cutoff = now() - timedelta(hours=limits["refresh_hours"])
        for saved in sorted(folder.parent.iterdir()) if folder.parent.exists() else []:
            try:
                captured_at = datetime.strptime(saved.name.split("-", 1)[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if captured_at < evidence_cutoff:
                continue
            for page in sorted((saved / "indeed-browser").glob("*-discovery.html")):
                discover(source, page.read_text(), "https://uk.indeed.com/jobs", rejected_ids=rejected)
        with connection.transaction():
            summary["artefact_queue_entries_suppressed"] += suppress_artefacts(connection, source, rejected, now())
    discovery_mode = limits.get("discovery", "always")
    preview = pending_tasks(connection, source, cutoff, limits["details"]) if discovery_mode == "auto" else []
    unfinished = connection.execute("SELECT 1 FROM crawl_progress WHERE source = %s AND completed_at IS NULL AND started_at > %s",
                                    (source, now() - timedelta(hours=limits["refresh_hours"]))).fetchone()
    skip_discovery = discovery_mode == "never" or (discovery_mode == "auto" and limits["details"] > 0
                                                 and len(preview) >= limits["details"] and not unfinished)
    summary["discovery_mode"] = discovery_mode
    summary["discovery_skipped"] = skip_discovery
    summary["discovery_skip_reason"] = "explicit_queue_drain" if discovery_mode == "never" else "sufficient_pending_work" if skip_discovery else None
    cycle = None
    auth_limited_pagination = False
    summary["resumed_cycle"] = False
    summary["cycle_id"] = None
    if not skip_discovery:
        cycle, resumed = begin_cycle(connection, source, queries, locations, limits["pages"], now(), limits["refresh_hours"])
        summary["resumed_cycle"] = resumed
        summary["cycle_id"] = str(cycle["cycle_id"])
        auth_limited_pagination = cycle["auth_limited"]

    def event(kind, **fields):
        with (folder / "events.jsonl").open("a") as output:
            output.write(json.dumps({"at": now().isoformat(), "source": source, "kind": kind, **fields}) + "\n")

    scopes = () if skip_discovery else ((query, location) for query in queries for location in locations)
    for query, location in scopes:
        state = load_checkpoint(connection, cycle, query, location, discovery_url(source, query, 0, location))
        url = state["next_url"]
        seen_pages = set(state["fingerprints"])
        seen_urls = set(state["urls"])
        seen_query_ids = set(state["ids"])
        progress = {"query": query, "location": location, "pages": 0, "unique_ids": len(seen_query_ids),
                    "pages_previously_fetched": state["next_page"], "status": state["status"]}
        summary["query_runs"].append(progress)
        if state["status"] != "running":
            if summary["status"] == "complete" and state["status"] != "no_next_link":
                summary["status"] = "limited"
            continue
        for page in range(state["next_page"], limits["pages"]):
            normalized_url = checkpoint_url(source, url)
            if normalized_url in seen_urls:
                progress["status"] = "pagination_loop"
                state["status"] = progress["status"]
                save_checkpoint(connection, cycle, query, location, state, now())
                summary["status"] = "partial"
                event("pagination_loop", url=url)
                break
            result = fetcher.fetch(source, "discovery", url)
            summary["pages_fetched"] += 1
            progress["pages"] += 1
            if not result.usable:
                auth_gate = result.blocked_reason == "logged_out_pagination_or_auth_gate"
                if auth_gate:
                    auth_limited_pagination = True
                    with connection.transaction():
                        connection.execute("UPDATE crawl_progress SET auth_limited = true WHERE source = %s", (source,))
                        state["status"] = "signin_limited"
                        save_checkpoint(connection, cycle, query, location, state, now())
                summary["status"] = "blocked" if result.blocked_reason and not auth_gate else "partial"
                summary["failures"] += 1
                progress["status"] = "signin_limited" if auth_gate else "blocked" if result.blocked_reason else "failed"
                event("discovery_failed", status=result.status, blocked_reason=result.blocked_reason, error_type=result.error_type)
                break
            artefacts, verified = set(), set()
            found, next_url = discover(source, result.text, result.url, rejected_ids=artefacts, verified_ids=verified)
            summary["discovery_artefacts_skipped"] += len(artefacts)
            fingerprint = hashlib.sha256(json.dumps(sorted(candidate.source_job_id for candidate in found)).encode()).hexdigest()
            if not found or fingerprint in seen_pages:
                summary["status"] = "partial"
                progress["status"] = "empty_results" if not found else "repeated_page"
                state["status"] = progress["status"]
                save_checkpoint(connection, cycle, query, location, state, now())
                event("empty_or_repeated_discovery", query=query, page=page)
                break
            seen_pages.add(fingerprint)
            seen_urls.add(normalized_url)
            page_ids = {candidate.source_job_id for candidate in found}
            summary["overlapping_sightings"] += len(page_ids & candidates.keys())
            seen_query_ids.update(page_ids)
            progress["unique_ids"] = len(seen_query_ids)
            event("discovery_page", query=query, location=location, page=page + 1,
                  observed_ids=len(page_ids), new_to_run=len(page_ids - candidates.keys()), next_link=bool(next_url))
            page_known = known_listings(connection, source, [candidate.source_job_id for candidate in found])
            for identity, row in page_known.items():
                known.setdefault(identity, row)
            forced = {identity for identity, row in page_known.items() if row["removed_at"] is not None}
            for candidate in found:
                row = page_known.get(candidate.source_job_id)
                if (row and candidate.source_job_id not in candidates and candidate.source_job_id not in forced
                        and candidate.source_job_id not in targets
                        and row["last_detail_refresh_at"] and row["last_detail_refresh_at"] > cutoff
                        and not (row["posted_at"] is None and candidate.posted_at is not None)):
                    summary["details_skipped_fresh"] += 1
            state.update(next_page=page + 1, ids=sorted(seen_query_ids), fingerprints=sorted(seen_pages), urls=sorted(seen_urls))
            if source in ("reed", "indeed") and not next_url:
                progress["status"] = "no_next_link"
            elif source == "indeed" and auth_limited_pagination:
                progress["status"] = "known_signin_page_limit"
                if summary["status"] == "complete":
                    summary["status"] = "limited"
            elif page + 1 == limits["pages"]:
                if summary["status"] == "complete":
                    summary["status"] = "limited"
                progress["status"] = "page_limit"
            state["status"] = progress["status"]
            following = next_url or discovery_url(source, query, page + 1, location, len(seen_query_ids))
            state["next_url"] = checkpoint_url(source, following)
            # Commit sightings, pending IDs/date hints and the next position together.
            with connection.transaction():
                summary["artefact_queue_entries_suppressed"] += suppress_artefacts(connection, source, artefacts, now())
                clear_verified_artefacts(connection, source, verified)
                observe(connection, source, counters, discovered=[candidate.source_job_id for candidate in found])
                queue_candidates(connection, source, found, now(), forced)
                save_checkpoint(connection, cycle, query, location, state, now())
            for candidate in found:
                candidates.setdefault(candidate.source_job_id, candidate)
            summary["discovered"] = len(candidates)
            if state["status"] != "running":
                break
            url = following
        if fetcher.blocked_by_source[source]:
            break
    # Refresh stored jobs even if search did not rediscover them. Oldest due jobs get priority.
    due = scheduled_details(connection, source, cutoff, limits["details"])
    queued = pending_tasks(connection, source, cutoff, limits["details"])
    summary["pending_details_loaded"] = len(queued)
    queued_by_id = {candidate.source_job_id: candidate for candidate in queued}
    tasks = {identity: queued_by_id.get(identity, Candidate(identity, row["url"])) for identity, row in targets.items()}
    known.update(targets)
    for row in due:
        tasks.setdefault(row["source_job_id"], queued_by_id.get(row["source_job_id"], Candidate(row["source_job_id"], row["url"], row.get("discovery_posted_at"))))
    for row in due:
        known.setdefault(row["source_job_id"], row)
    known.update(known_listings(connection, source, queued_by_id))
    for candidate in queued:
        tasks.setdefault(candidate.source_job_id, candidate)
    rejected = Counter()
    for identity, candidate in tasks.items():
        if fetcher.blocked_by_source[source]:
            summary["status"] = "blocked"
            break
        if summary["details_fetched"] >= limits["details"]:
            if summary["status"] == "complete":
                summary["status"] = "limited"
            break
        attempt_candidate(connection, source, identity, now())
        result = fetcher.fetch(source, "detail", candidate.url)
        summary["details_fetched"] += 1
        if result.status in (404, 410) and not result.blocked_reason and not result.error_type:
            confirmation = fetcher.fetch(source, "removal_confirmation", candidate.url)
            summary["removal_confirmations"] += 1
            try:
                matches = source_id(source, result.url) == identity and source_id(source, confirmation.url) == identity
            except ExtractionError:
                matches = False
            if confirmation.status in (404, 410) and not confirmation.blocked_reason and not confirmation.error_type and matches:
                with connection.transaction():
                    changes = Counter()
                    observe(connection, source, changes, removed=[identity])
                    acknowledge(connection, source, identity)
                counters.update(changes)
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
                with connection.transaction():
                    changes = Counter()
                    observe(connection, source, changes, removed=[identity])
                    acknowledge(connection, source, identity)
                counters.update(changes)
                event("explicit_expiry", source_job_id=identity)
                continue
            previous = known.get(identity, {}).get("posted_at") or candidate.posted_at
            listing = parse_detail(source, result.text, result.url, now(), previous, result.rendered_metadata)
        except IneligibleListing as exc:
            reason = str(exc)
            rejected[reason] += 1
            with connection.transaction():
                connection.execute(
                    "INSERT INTO listing_exclusions (source, source_job_id, checked_at, reason) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (source, source_job_id) DO UPDATE SET checked_at = EXCLUDED.checked_at, reason = EXCLUDED.reason",
                    (source, identity, now(), reason),
                )
                acknowledge(connection, source, identity)
            event("ineligible", source_job_id=identity, reason=reason)
            continue
        except ValueError as exc:
            observe(connection, source, counters, failed=[identity])
            summary["failures"] += 1
            summary["status"] = "partial"
            event("extraction_failed", source_job_id=identity, error_type=type(exc).__name__, reason=str(exc))
            continue
        with connection.transaction():
            changes = Counter()
            observe(connection, source, changes, details=[listing])
            connection.execute("DELETE FROM listing_exclusions WHERE source = %s AND source_job_id = %s", (source, identity))
            acknowledge(connection, source, identity)
        counters.update(changes)
        summary["accepted"] += 1
        event("stored", source_job_id=identity, content_hash=listing.content_hash)
    summary["rejected"] = dict(rejected)
    if cycle:
        connection.execute("UPDATE crawl_progress SET completed_at = %s WHERE source = %s AND cycle_id = %s",
                           (now(), source, cycle["cycle_id"]))
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
    queries = [value.strip() for value in os.environ.get("CRAWL_QUERIES", "software engineer,data engineer").split(",") if value.strip()]
    if not queries:
        raise ValueError("CRAWL_QUERIES cannot be empty")
    locations = [value.strip() for value in os.environ.get("CRAWL_LOCATIONS", "United Kingdom").split(",") if value.strip()]
    if not locations:
        raise ValueError("CRAWL_LOCATIONS cannot be empty")
    queries, locations = list(dict.fromkeys(queries)), list(dict.fromkeys(locations))
    refresh_ids = list(dict.fromkeys(value.strip() for value in os.environ.get("CRAWL_REFRESH_IDS", "").split(",") if value.strip()))
    if any(not re.fullmatch(r"(?:linkedin|reed):[0-9]+|indeed:[\w-]+", identity)
           or identity.split(":", 1)[0] not in sources for identity in refresh_ids):
        raise ValueError("CRAWL_REFRESH_IDS must contain source:id values from configured sources")
    discovery_mode = os.environ.get("CRAWL_DISCOVERY", "auto")
    if discovery_mode not in ("auto", "always", "never"):
        raise ValueError("CRAWL_DISCOVERY must be auto, always or never")
    limits = {"pages": integer_setting("CRAWL_MAX_PAGES", 2),
              "details": integer_setting("CRAWL_MAX_DETAILS", 20, 0),
              "refresh_hours": integer_setting("DETAIL_REFRESH_HOURS", 24), "discovery": discovery_mode}
    source_limits = {source: {**limits, "pages": min(limits["pages"], integer_setting("INDEED_MAX_PAGES", 1))}
                     if source == "indeed" else dict(limits) for source in sources}
    folder = Path("output/runs") / (now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    fetcher = Fetcher(folder, max_requests=integer_setting("CRAWL_MAX_REQUESTS", 300),
                      max_seconds=integer_setting("CRAWL_MAX_SECONDS", 600),
                       delay=float(os.environ.get("CRAWL_REQUEST_DELAY", "2")),
                      save_pages=os.environ.get("CRAWL_SAVE_PAGES") == "1")
    counters = Counter({"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0})
    report = {"started_at": now(), "source_runs": {source: {"status": "not_started"} for source in sources},
              "limits": limits, "queries": queries, "locations": locations, "status": "finished",
              "indeed_resource_policy": os.environ.get("INDEED_RESOURCE_POLICY", "lean"),
              "force_detail_refresh": os.environ.get("CRAWL_FORCE_REFRESH") == "1", "refresh_ids": refresh_ids,
              "limits_by_source": source_limits}
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
                        crawl_source(connection, fetcher, folder, source, queries, source_limits[source], counters, locations,
                                     summary=report["source_runs"][source], refresh_ids=refresh_ids)
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
                report["efficiency"] = efficiency(report)
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
