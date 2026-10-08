"""Version-1 fixture runner. Uses Postgres and local files, never source URLs."""

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from crawler.models import Observation, timestamp
from crawler.reconcile import reconcile, stored_rows
from tests.support import isolated_database


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_rows(name, expected, actual, history, previous):
    require(set(actual) == set(expected),
            f"{name}: row IDs differ: expected {sorted(expected)}, got {sorted(actual)}")
    for identity, assertions in expected.items():
        row = actual[identity]
        for field, value in assertions.items():
            if field == "content_hash_equals_run":
                if value is not None:
                    require(value in history and identity in history[value],
                            f"{name}: unknown hash reference {value!r} for {identity}")
                    require(row["content_hash"] == history[value][identity]["content_hash"],
                            f"{name}: {identity} hash differs from run {value}")
                elif identity in previous:
                    require(row["content_hash"] != previous[identity]["content_hash"],
                            f"{name}: {identity} expected new content but hash did not change")
                continue
            require(field in row, f"{name}: unknown expected column {field}")
            stored = row[field]
            if isinstance(stored, datetime) and value is not None:
                value = timestamp(value)
            elif isinstance(stored, Decimal) and value is not None:
                value = Decimal(str(value))
            require(stored == value,
                    f"{name}: {identity}.{field}: expected {value!r}, got {stored!r}")
        require(bool(row["content_hash"]) and bool(row["canonical_job_id"]),
                f"{name}: {identity} missing hash/canonical ID")


def run_fixture(path):
    fixture = json.loads(Path(path).read_text())
    require(fixture.get("version") == 1, "Unsupported lifecycle fixture version")
    require(isinstance(fixture.get("runs"), list) and fixture["runs"], "Fixture has no runs")
    history = {}
    with isolated_database() as connection:
        for raw in fixture["runs"]:
            name = raw["name"]
            require(name not in history, f"Duplicate fixture run name: {name}")
            observation = Observation.from_dict(raw)
            previous = stored_rows(connection)
            report = reconcile(connection, observation)
            expected = raw["expected"]
            for key, value in expected["report"].items():
                require(key in report, f"{name}: unsupported expected report field {key}")
                require(report[key] == value, f"{name}: {key}: expected {value}, got {report[key]}")
            rows = stored_rows(connection)
            assert_rows(name, expected["rows"], rows, history, previous)
            refresh_before = connection.execute("SELECT * FROM listing_state ORDER BY job_id").fetchall()
            second_report = reconcile(connection, observation)
            require(all(value == 0 for value in second_report.values()),
                    f"{name}: replay counts are not zero: {second_report}")
            require(stored_rows(connection) == rows, f"{name}: replay changed stored rows")
            require(connection.execute("SELECT * FROM listing_state ORDER BY job_id").fetchall() == refresh_before,
                    f"{name}: replay changed refresh bookkeeping")
            history[name] = rows
            print(f"PASS {name}: {report}; replay unchanged")
    print(f"Passed {len(history)} fixture runs and their replays; isolated database removed")


if __name__ == "__main__":
    run_fixture(os.environ.get("FIXTURE_PATH", "tests/fixtures/lifecycle.json"))
