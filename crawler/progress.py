"""Durable public discovery checkpoints and pending detail work; no job-content writes."""

import hashlib
import json
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from psycopg.types.json import Jsonb

from crawler.parsers import Candidate


def checkpoint_url(source, url):
    """Retain search semantics, never session/tracking parameters or credentials."""
    parsed = urlsplit(url)
    hosts = {"linkedin": {"www.linkedin.com", "uk.linkedin.com"},
             "reed": {"www.reed.co.uk"}, "indeed": {"uk.indeed.com"}}
    if parsed.scheme != "https" or parsed.username or parsed.hostname not in hosts[source] or not parsed.path.startswith("/jobs"):
        raise ValueError("Unsafe discovery checkpoint URL")
    keys = {"linkedin": {"keywords", "location", "start"},
            "reed": {"keywords", "locationName", "pageno", "sortBy", "distance", "proximity"},
            "indeed": {"q", "l", "start", "radius", "sort", "fromage", "jt", "filter", "sc", "limit"}}[source]
    return urlunsplit((parsed.scheme, parsed.hostname, parsed.path,
                      urlencode(sorted((key, value) for key, value in parse_qsl(parsed.query) if key in keys)), ""))


def begin_cycle(connection, source, queries, locations, pages, observed_at, refresh_hours):
    # Version changes intentionally invalidate traversal positions, not pending IDs.
    plan = json.dumps([1, queries, locations, pages], separators=(",", ":"))
    plan_hash = hashlib.sha256(plan.encode()).hexdigest()
    previous = connection.execute("SELECT * FROM crawl_progress WHERE source = %s", (source,)).fetchone()
    if previous and previous["completed_at"] is None and previous["plan_hash"] == plan_hash and previous["started_at"] > observed_at - timedelta(hours=refresh_hours):
        return previous, True
    cycle = {"source": source, "cycle_id": uuid4(), "plan_hash": plan_hash,
             "started_at": observed_at, "auth_limited": False}
    connection.execute(
        "INSERT INTO crawl_progress (source, cycle_id, plan_hash, started_at) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (source) DO UPDATE SET cycle_id = EXCLUDED.cycle_id, plan_hash = EXCLUDED.plan_hash, "
        "started_at = EXCLUDED.started_at, completed_at = NULL, auth_limited = false",
        (source, cycle["cycle_id"], plan_hash, observed_at),
    )
    return cycle, False


def load_checkpoint(connection, cycle, query, location, url):
    row = connection.execute(
        "SELECT state FROM discovery_checkpoints WHERE source = %s AND query = %s AND location = %s AND cycle_id = %s",
        (cycle["source"], query, location, cycle["cycle_id"]),
    ).fetchone()
    return row["state"] if row else {"next_page": 0, "next_url": checkpoint_url(cycle["source"], url),
                                    "ids": [], "fingerprints": [], "urls": [], "status": "running"}


def save_checkpoint(connection, cycle, query, location, state, observed_at):
    connection.execute(
        "INSERT INTO discovery_checkpoints (source, query, location, cycle_id, state, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (source, query, location) DO UPDATE "
        "SET cycle_id = EXCLUDED.cycle_id, state = EXCLUDED.state, updated_at = EXCLUDED.updated_at",
        (cycle["source"], query, location, cycle["cycle_id"], Jsonb(state), observed_at),
    )


def queue_candidates(connection, source, candidates, observed_at, forced=()):
    forced = set(forced)
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO pending_candidates (source, source_job_id, url, posted_at, first_discovered_at, last_discovered_at, force_detail) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (source, source_job_id) DO UPDATE SET "
            "url = EXCLUDED.url, posted_at = COALESCE(EXCLUDED.posted_at, pending_candidates.posted_at), "
            "last_discovered_at = GREATEST(pending_candidates.last_discovered_at, EXCLUDED.last_discovered_at), "
            "force_detail = pending_candidates.force_detail OR EXCLUDED.force_detail",
            [(source, item.source_job_id, item.url, item.posted_at, observed_at, observed_at, item.source_job_id in forced)
             for item in candidates],
        )


def suppress_artefacts(connection, source, identities, observed_at):
    """Suppress pending UI artefacts only; never delete or mark a stored job removed."""
    if not identities:
        return 0
    eligible = connection.execute(
        "SELECT unnest(%s::text[]) AS identity EXCEPT SELECT source_job_id FROM jobs WHERE source = %s",
        (sorted(identities), source),
    ).fetchall()
    for row in eligible:
        identity = row["identity"]
        connection.execute(
            "INSERT INTO listing_exclusions (source, source_job_id, checked_at, reason) VALUES (%s, %s, %s, 'hidden_discovery_artefact') "
            "ON CONFLICT (source, source_job_id) DO UPDATE SET checked_at = EXCLUDED.checked_at, reason = EXCLUDED.reason",
            (source, identity, observed_at),
        )
    identities = [row["identity"] for row in eligible]
    if not identities:
        return 0
    removed = connection.execute("DELETE FROM pending_candidates WHERE source = %s AND source_job_id = ANY(%s)",
                                 (source, identities))
    return removed.rowcount


def clear_verified_artefacts(connection, source, identities):
    if identities:
        connection.execute(
            "DELETE FROM listing_exclusions WHERE source = %s AND source_job_id = ANY(%s) AND reason = 'hidden_discovery_artefact'",
            (source, list(identities)),
        )


def pending_tasks(connection, source, cutoff, limit):
    # Fresh, fully populated rows and recently rejected adverts need no queued request.
    connection.execute(
        "DELETE FROM pending_candidates p WHERE p.source = %s AND ("
        "EXISTS (SELECT 1 FROM listing_exclusions e WHERE e.source = p.source AND e.source_job_id = p.source_job_id AND e.checked_at > %s) OR "
        "EXISTS (SELECT 1 FROM jobs j JOIN listing_state s ON s.job_id = j.id "
        "WHERE j.source = p.source AND j.source_job_id = p.source_job_id AND j.removed_at IS NULL "
        "AND s.last_detail_refresh_at > %s AND NOT p.force_detail AND NOT (j.posted_at IS NULL AND p.posted_at IS NOT NULL)))",
        (source, cutoff, cutoff),
    )
    rows = connection.execute(
        "SELECT p.* FROM pending_candidates p LEFT JOIN jobs j ON j.source = p.source AND j.source_job_id = p.source_job_id "
        "WHERE p.source = %s ORDER BY (j.id IS NULL), COALESCE(p.last_attempt_at, p.first_discovered_at), p.first_discovered_at, p.source_job_id LIMIT %s",
        (source, limit),
    ).fetchall()
    return [Candidate(row["source_job_id"], row["url"], row["posted_at"]) for row in rows]


def attempt_candidate(connection, source, identity, observed_at):
    connection.execute("UPDATE pending_candidates SET last_attempt_at = %s, attempts = attempts + 1 WHERE source = %s AND source_job_id = %s",
                       (observed_at, source, identity))


def acknowledge(connection, source, identity):
    connection.execute("DELETE FROM pending_candidates WHERE source = %s AND source_job_id = %s", (source, identity))


def pending_count(connection, source):
    return connection.execute("SELECT count(*) AS count FROM pending_candidates WHERE source = %s", (source,)).fetchone()["count"]
