"""Explicit source-evidenced repair of an incorrectly imported overseas relocation advert.

Archive the complete row; this is not source expiry, a crawl reset or absence-based removal.
No network requests are made. Only identity/content-matched relocation evidence is accepted.
"""

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from crawler.accuracy_review import description_tokens, evidence
from crawler.database import connect, database_url, initialize
from crawler.parsers import non_uk_relocation


def quarantine_relocation(connection, identity, capture, markup):
    source = identity.split(":", 1)[0]
    item = evidence(source, markup)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(74201931)")
        row = connection.execute("SELECT * FROM jobs WHERE id=%s FOR UPDATE", (identity,)).fetchone()
        if row is None:
            return False
        if (not item or item["id"] != identity or item["title"] != row["title"]
                or description_tokens(markup, source) != re.findall(r"\w+", row["description"].casefold())
                or not non_uk_relocation(row["title"], item["source_description"])):
            raise ValueError("Quarantine requires identity/content-matched explicit non-UK relocation evidence")
        peers = connection.execute("SELECT count(*) AS count FROM jobs WHERE canonical_job_id=%s", (row["canonical_job_id"],)).fetchone()["count"]
        if peers != 1:
            raise ValueError("Grouped listing requires separate canonical repair review")
        observed = datetime.now(timezone.utc)
        connection.execute("INSERT INTO listing_quarantine (job_id, reason, evidence_capture, snapshot, quarantined_at) "
                           "SELECT id, 'non_uk_relocation', %s, to_jsonb(j), %s FROM jobs j WHERE id=%s ON CONFLICT (job_id) DO NOTHING",
                           (str(capture), observed, identity))
        connection.execute("DELETE FROM dedupe_evidence WHERE left_id=%s OR right_id=%s", (identity, identity))
        for table in ("listing_state", "dedupe_features", "listing_match_evidence"):
            connection.execute(f"DELETE FROM {table} WHERE job_id=%s", (identity,))
        connection.execute("DELETE FROM pending_candidates WHERE source=%s AND source_job_id=%s", (source, row["source_job_id"]))
        connection.execute("INSERT INTO listing_exclusions (source, source_job_id, checked_at, reason) VALUES (%s,%s,%s,'non_uk_relocation') "
                           "ON CONFLICT (source,source_job_id) DO UPDATE SET checked_at=EXCLUDED.checked_at, reason=EXCLUDED.reason",
                           (source, row["source_job_id"], observed))
        connection.execute("DELETE FROM jobs WHERE id=%s", (identity,))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    with connect(database_url()) as connection:
        initialize(connection)
        if not connection.execute("SELECT pg_try_advisory_lock(74201932) AS locked").fetchone()["locked"]:
            raise RuntimeError("A crawl is already running")
        changed = quarantine_relocation(connection, args.id, args.capture, args.capture.read_text())
    print(f"Quarantined with full row retained: {args.id}" if changed else "No active row to quarantine")
    print("Next make crawl rewrites exports; no source removal transition is claimed")


if __name__ == "__main__":
    main()
