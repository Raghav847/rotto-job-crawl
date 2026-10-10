"""Offline aggregation of captured browser traffic for efficiency review."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


def summarize(path):
    records = [json.loads(line) for line in path.read_text().splitlines()]
    counts, sizes = Counter(), Counter()
    phases = defaultdict(Counter)
    urls = Counter()
    for row in records:
        host = urlsplit(row["url"]).hostname or "unknown"
        kind = row.get("resource_type", "http_document")
        key = f"{kind}:{host}"
        counts[key] += 1
        sizes[key] += row["response_bytes"]
        phases[row["kind"]]["requests"] += 1
        phases[row["kind"]]["bytes"] += row["response_bytes"]
        urls[(host, urlsplit(row["url"]).path)] += 1
    return {"log": str(path), "requests": len(records), "decoded_bytes": sum(sizes.values()),
            "phases": dict(phases), "resources": [
                {"bucket": key, "requests": counts[key], "bytes": sizes[key]}
                for key in sorted(counts, key=lambda value: sizes[value], reverse=True)],
            "repeated_resources": [{"host": host, "path": url, "count": count}
                                   for (host, url), count in urls.most_common(12) if count > 1]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.logs:
        print(json.dumps(summarize(path), indent=2))
