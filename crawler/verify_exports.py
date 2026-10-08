"""Check local exports against Postgres and this run's request log, offline."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from crawler.database import connect, database_url
from crawler.exporting import json_value
from crawler.models import Listing
from crawler.reconcile import stored_rows


def main():
    report = json.loads(Path("output/report.json").read_text())
    exported = {}
    digest = hashlib.sha256()
    with Path("output/jobs.jsonl").open() as stream:
        for line in stream:
            digest.update(line.encode())
            row = json.loads(line)
            if row["id"] in exported:
                raise AssertionError("Duplicate exported source row")
            if Listing.from_dict(row).content_hash != row["content_hash"]:
                raise AssertionError(f"Content hash mismatch: {row['id']}")
            exported[row["id"]] = row
    if digest.hexdigest() != report["jobs_export_sha256"]:
        raise AssertionError("Report describes a different jobs export")
    with connect(database_url()) as connection:
        expected = json.loads(json.dumps(stored_rows(connection), default=json_value))
    if exported != expected:
        raise AssertionError("Export differs from persisted rows")
    requests = [json.loads(line) for line in Path(report["request_log"]).read_text().splitlines()]
    statuses = Counter(str(row["status"]) if row["status"] is not None else "error:" + row["error_type"] for row in requests)
    if len(requests) != report["requests_total"] or dict(statuses) != report["requests_by_status"]:
        raise AssertionError("Request counts differ from request log")
    if sum(bool(row["blocked_reason"]) for row in requests) != report["requests_blocked"]:
        raise AssertionError("Blocked count differs from request log")
    live = {source: 0 for source in ("indeed", "linkedin", "reed")}
    for row in exported.values():
        if row["removed_at"] is None:
            live[row["source"]] += 1
    if live != report["jobs_by_source"]:
        raise AssertionError("Live source counts differ from exported rows")
    canonical_live = {row["canonical_job_id"] for row in exported.values() if row["removed_at"] is None}
    groups = Counter(row["canonical_job_id"] for row in exported.values())
    if len(canonical_live) != report["canonical_jobs_live"]:
        raise AssertionError("Canonical live count differs from exported rows")
    if sum(size - 1 for size in groups.values()) != report["duplicates_linked"]:
        raise AssertionError("Duplicate link count differs from exported rows")
    print(f"Verified {len(exported)} exported rows, hashes, live counts, and {len(requests)} logged requests")


if __name__ == "__main__":
    main()
