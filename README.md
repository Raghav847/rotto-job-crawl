# Rotto UK job crawler

Python crawler for Indeed UK, LinkedIn and Reed with Postgres reconciliation,
offline lifecycle tests, and JSONL/report exports. Requires Docker Compose and Make;
Python, pinned dependencies, Chromium and its system libraries run in a Docker image.

## Run

Supply `PROXY_URL` or `PROXY_HOST` / `PROXY_PORT` / `PROXY_USERNAME` / `PROXY_PASSWORD`
through the environment or an ignored `.env`. Credentials are never embedded in code.

```sh
docker compose up -d
make crawl
make test
FIXTURE_PATH=/path/to/file.json make test
```

The first crawl builds the runtime automatically. Postgres 17 retains data in a
named volume; local port is `55432`, database/user/password `rotto/rotto/rotto-local`.
Configure `POSTGRES_*` before first initialization. Tests use the built image offline,
create fresh `rotto_test_<uuid>` databases, and drop only those databases. They assert
exact rows, prior-run hashes and counts, then replay each run with no changes.

## Access and extraction

LinkedIn/Reed use Chrome-impersonated HTTP. Indeed uses a persistent headless Chromium
session, UK locale/timezone, normal Chrome user-agent token, automation compatibility
flags, homepage warmup and Oxylabs' documented sticky-session username parameter.
Credentials and the proxy endpoint remain environment-configured. Public search's
selected job pane supplies the full description; `vjk` selects further jobs. No
accounts, CAPTCHA interactions/solving services, other proxies or runtime LLM calls.

HTTP alone, the legacy headless browser, and browser-to-HTTP cookie handoff failed
against Indeed protection; direct `viewjob` navigation also hit an anonymous auth gate.
Browser assets cost requests/bandwidth, so HTTP sources run first. Images, fonts, media
and bulky Indeed stylesheets are blocked locally. Logos are stored as URLs only,
including explicit branding JSON; company banners are not mistaken for logos.

Parsers bind full details to board-owned IDs, verify UK eligibility, preserve source
titles/locations, and exclude Reed training adverts. Missing fields stay null.
Contract/temporary takes precedence over working hours; “permanent” alone does not
establish full-time hours. Relative posting dates are estimated once; exact source
dates are preferred. Full descriptions exclude navigation and recommendations.

## Persistence and limits

Successful observations commit incrementally; first seen is preserved, sightings
advance last seen, and edited content changes its SHA-256 hash. Details refresh every
24 hours, oldest due first, including jobs absent from search. Failed refreshes remain
due. Removal requires explicit expiry or confirmed source not-found; search absence,
incomplete runs and inline-search endpoint errors never authorize removal. Reappearance
clears removal. Transactions and a live-run lock protect data and exports.

Defaults: one page/query, ten details/source, 300 requests and ten minutes; configure
`CRAWL_QUERIES`, `CRAWL_MAX_*` and `DETAIL_REFRESH_HOURS`. Limits/blocking report partial
coverage. All three integrations have produced real jobs; cross-board dedupe and scale
tuning remain in progress. Canonical IDs currently remain stable per source listing.

Each run rewrites `output/jobs.jsonl` (all stored rows, including removed) and
`output/report.json`; source totals are live database counts, lifecycle counts per-run.
`duplicates_linked` counts copies beyond one per stored canonical group. Request logs
are under ignored `output/runs/`. Set `PROXY_COST_PER_GB_USD` for estimated cost and cost
per 1,000 page-request attempts; both are null while the rate is unknown. Decoded body
bytes are an estimate, not billed traffic. Verify exports with
`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`.
