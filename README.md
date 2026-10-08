# Rotto UK job crawler

Python crawler with Postgres reconciliation, full-detail LinkedIn/Reed parsing,
offline lifecycle tests, and JSONL/report exports. Indeed currently returns a
managed challenge; access experiments are in [`access-findings.md`](access-findings.md).

## Run

Requires Docker Compose, Python 3.13+, and `uv`. Supply proxy credentials through
`PROXY_URL` or `PROXY_HOST` / `PROXY_PORT` / `PROXY_USERNAME` / `PROXY_PASSWORD`;
an ignored `.env` is supported and environment variables take precedence.

```sh
docker compose up -d
uv sync --locked
make crawl
make test
FIXTURE_PATH=/path/to/file.json make test
```

Postgres 17 uses a persistent volume and `127.0.0.1:55432` by default; local
database/user/password are `rotto` / `rotto` / `rotto-local`. Configure `POSTGRES_*`
before first initialization, or override the client with `DATABASE_URL`.
Schema initialization is automatic. Tests run offline after dependency setup,
create fresh `rotto_test_<uuid>` databases, and remove only those databases.
They assert exact rows, content hashes, counts, and unchanged second applications.

## Approach and tradeoffs

Fetching, parsing, persistence, and exports are separate modules. Chrome-impersonated
HTTP through the supplied proxy worked for LinkedIn/Reed; it failed against
Indeed's JavaScript challenge. Fetching uses timeouts, up to three transient-error
attempts with backoff, explicitly logged redirects, request/time budgets, and stops
a source after a challenge. Successful observations commit incrementally; reruns
resume through idempotent writes. A session lock prevents overlapping live runs.

Parsers verify board-owned IDs, preserve visible titles/locations, extract only the
full description, retain nulls for unavailable fields, and require UK eligibility.
Reed training-course adverts are excluded. Contract/temporary takes precedence over
full-/part-time when both are shown. Relative posting dates are estimated once and
preserved on refresh unless an exact source date is available.

No reliable full-content revision signal has been verified yet. Details refresh
every 24 hours (`DETAIL_REFRESH_HOURS`), including stored jobs absent from search;
oldest due listings get priority within the configured budget. Fresh sightings
advance last seen without fetching details. Failed refreshes remain due; rejected
listings are rechecked after the same interval. Removal requires explicit expiry
or two matching source not-found responses; search absence never removes a row.

Defaults: one page per query, ten detail fetches per source, 100 requests, ten
minutes, and a one-second request gap. Adjust `CRAWL_QUERIES` and `CRAWL_MAX_*` to
expand coverage. Runs reaching limits report partial coverage. Source coverage,
cross-board matching, and scale tuning remain in progress; canonical IDs currently
remain stable per source listing.

Every live run rewrites `output/jobs.jsonl` (all rows, including removed) and
`output/report.json`; live source totals and per-run lifecycle counts are separate.
`duplicates_linked` counts stored copies beyond one per canonical group. Logs and
optional page samples are under ignored `output/runs/`. Set `PROXY_COST_PER_GB_USD`
for estimated cost and cost per 1,000 requests; costs are null while the rate is
unknown. Decoded body bytes are an estimate, not proxy-billed traffic. Verify local
exports with `uv run --locked python -m crawler.verify_exports`.
