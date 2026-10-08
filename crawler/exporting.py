"""Snapshot exports of all stored rows and the current run's report."""

import hashlib
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot export value of type {type(value).__name__}")


def export_run(connection, report, folder=Path("output")):
    folder.mkdir(parents=True, exist_ok=True)
    jobs_temp = None
    report_temp = None
    try:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            counts = connection.execute(
                "SELECT source, count(*) AS total FROM jobs WHERE removed_at IS NULL GROUP BY source"
            ).fetchall()
            report["jobs_by_source"] = {source: 0 for source in ("indeed", "linkedin", "reed")}
            report["jobs_by_source"].update({row["source"]: row["total"] for row in counts})
            report["canonical_jobs_live"] = connection.execute(
                "SELECT count(DISTINCT canonical_job_id) AS total FROM jobs WHERE removed_at IS NULL"
            ).fetchone()["total"]
            report["duplicates_linked"] = int(connection.execute(
                "SELECT COALESCE(sum(size - 1), 0) AS total FROM "
                "(SELECT count(*) AS size FROM jobs GROUP BY canonical_job_id HAVING count(*) > 1) groups"
            ).fetchone()["total"])
            checksum = hashlib.sha256()
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as output:
                jobs_temp = Path(output.name)
                with connection.cursor(name="export_jobs") as rows:
                    rows.execute("SELECT * FROM jobs ORDER BY id")
                    for row in rows:
                        line = json.dumps(row, default=json_value, ensure_ascii=False, sort_keys=True) + "\n"
                        checksum.update(line.encode())
                        output.write(line)
            report["jobs_export_sha256"] = checksum.hexdigest()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as output:
            report_temp = Path(output.name)
            json.dump(report, output, default=json_value, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(jobs_temp, folder / "jobs.jsonl")
        os.replace(report_temp, folder / "report.json")
    finally:
        for path in (jobs_temp, report_temp):
            if path:
                path.unlink(missing_ok=True)
