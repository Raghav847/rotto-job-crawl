"""Explicit per-run efficiency and cost units; never infer proxy billing or a rate."""


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def efficiency(report):
    by_source = {}
    for source, run in report.get("source_runs", {}).items():
        requests = report.get("requests_by_source", {}).get(source, 0)
        size = report.get("response_bytes_by_source", {}).get(source, 0)
        accepted = run.get("accepted", 0)
        by_source[source] = {
            "accepted_detail_observations": accepted, "new_listings": run.get("jobs_new", 0),
            "requests": requests, "decoded_bytes": size,
            "accepted_per_request": ratio(accepted, requests),
            "decoded_bytes_per_accepted": ratio(size, accepted),
            "block_rate": ratio(report.get("blocked_requests_by_source", {}).get(source, 0), requests),
            "discovery_skipped": run.get("discovery_skipped", False),
        }
    accepted = sum(item["accepted_detail_observations"] for item in by_source.values())
    fetches = sum(run.get("pages_fetched", 0) + run.get("details_fetched", 0) + run.get("removal_confirmations", 0)
                  for run in report.get("source_runs", {}).values())
    size, requests = report.get("response_body_bytes", 0), report.get("requests_total", 0)
    elapsed = (report["finished_at"] - report["started_at"]).total_seconds()
    cost = report.get("estimated_cost_usd")
    return {"runtime_seconds": elapsed, "accepted_detail_observations": accepted,
            "new_listings": report.get("jobs_new", 0), "listing_page_fetches": fetches,
            "accepted_per_request": ratio(accepted, requests),
            "new_per_request": ratio(report.get("jobs_new", 0), requests),
            "decoded_bytes_per_accepted": ratio(size, accepted),
            "new_per_decoded_gb": ratio(report.get("jobs_new", 0) * 1_000_000_000, size),
            "accepted_per_minute": ratio(accepted * 60, elapsed),
            "cost_per_1000_listing_fetches_usd": ratio(cost * 1000, fetches) if cost is not None else None,
            "cost_per_1000_request_attempts_usd": ratio(cost * 1000, requests) if cost is not None else None,
            "traffic_basis": "Decoded response bodies, not proxy-billed bytes; listing fetches exclude warmup/resources but their traffic is included",
            "by_source": by_source}
