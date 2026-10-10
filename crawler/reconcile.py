"""Transactional, evidence-based persistence of normalized source observations."""

from uuid import NAMESPACE_URL, uuid5

from psycopg import sql

from crawler.models import CONTENT_FIELDS, Observation, job_id
from crawler.dedupe import deduplicate_listing


def reconcile(connection, observation: Observation):
    counts = {"jobs_new": 0, "jobs_changed": 0, "jobs_removed": 0}
    observed_at = observation.observed_at
    with connection.transaction():
        # Serialize reconciliation transactions, including first-insert races.
        connection.execute("SELECT pg_advisory_xact_lock(74201931)")
        for listing in observation.details:
            row = connection.execute(
                "SELECT j.*, s.last_detail_refresh_at FROM jobs j "
                "LEFT JOIN listing_state s ON s.job_id = j.id WHERE j.id = %s FOR UPDATE OF j",
                (listing.id,),
            ).fetchone()
            if row is None:
                columns = ("id", *CONTENT_FIELDS, "canonical_job_id", "content_hash", "first_seen_at", "last_seen_at")
                values = (listing.id, *(listing.content[field] for field in CONTENT_FIELDS),
                          str(uuid5(NAMESPACE_URL, listing.id)), listing.content_hash, observed_at, observed_at)
                connection.execute(sql.SQL("INSERT INTO jobs ({}) VALUES ({})").format(
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                ), values)
                counts["jobs_new"] += 1
            else:
                # A delayed batch must not overwrite newer details or removal evidence.
                if row["last_detail_refresh_at"] and observed_at < row["last_detail_refresh_at"]:
                    continue
                if row["removed_at"] and observed_at < row["removed_at"]:
                    continue
                if row["content_hash"] != listing.content_hash:
                    connection.execute(sql.SQL("UPDATE jobs SET {}, content_hash = %s WHERE id = %s").format(
                        sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(field)) for field in CONTENT_FIELDS),
                    ), (*(listing.content[field] for field in CONTENT_FIELDS), listing.content_hash, listing.id))
                    counts["jobs_changed"] += 1
            connection.execute(
                "INSERT INTO listing_state (job_id, last_detail_refresh_at) VALUES (%s, %s) "
                "ON CONFLICT (job_id) DO UPDATE SET last_detail_refresh_at = EXCLUDED.last_detail_refresh_at "
                "WHERE listing_state.last_detail_refresh_at < EXCLUDED.last_detail_refresh_at",
                (listing.id, observed_at),
            )
            if listing.matching_evidence is not None:
                evidence = listing.matching_evidence
                connection.execute(
                    "INSERT INTO listing_match_evidence (job_id, content_hash, kind, issuer, reference) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (job_id) DO UPDATE SET content_hash = EXCLUDED.content_hash, kind = EXCLUDED.kind, "
                    "issuer = EXCLUDED.issuer, reference = EXCLUDED.reference",
                    (listing.id, listing.content_hash, evidence["kind"], evidence["issuer"], evidence["reference"]),
                )

        live_ids = observation.discovered | {listing.content["source_job_id"] for listing in observation.details}
        for source_id in sorted(live_ids):
            connection.execute(
                "UPDATE jobs SET last_seen_at = GREATEST(last_seen_at, %s), removed_at = NULL "
                "WHERE id = %s AND (removed_at IS NULL OR removed_at <= %s) "
                "AND (last_seen_at < %s OR removed_at IS NOT NULL)",
                (observed_at, job_id(observation.source, source_id), observed_at, observed_at),
            )
        # Traversal completion and search absence are deliberately not removal signals.
        for source_id in sorted(observation.confirmed_removed):
            result = connection.execute(
                "UPDATE jobs SET removed_at = %s WHERE id = %s AND removed_at IS NULL AND last_seen_at <= %s",
                (observed_at, job_id(observation.source, source_id), observed_at),
            )
            counts["jobs_removed"] += result.rowcount
        for listing in observation.details:
            deduplicate_listing(connection, listing.id)
    return counts


def stored_rows(connection):
    return {row["id"]: row for row in connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()}
