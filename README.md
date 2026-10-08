# Rotto UK job crawler

Python crawler for Indeed UK, LinkedIn and Reed. Requires Docker Compose and Make;
the pinned Docker image supplies Python, dependencies, Chromium and system libraries.

## Run

Set `PROXY_URL` or `PROXY_HOST` / `PROXY_PORT` / `PROXY_USERNAME` / `PROXY_PASSWORD`
in the environment or ignored `.env`; credentials are never embedded in code.

```sh
docker compose up -d
make crawl
make test
FIXTURE_PATH=/path/to/file.json make test
```

The first crawl builds the runtime. Postgres 17 uses a persistent volume, local port
`55432` and database/user/password `rotto/rotto/rotto-local`; configure `POSTGRES_*`
before initial setup. Tests use the built image offline, create fresh UUID-named
databases, and drop only those databases. They check rows, hashes, counts and replay.

## Access and accuracy

LinkedIn/Reed use Chrome-impersonated HTTP. Indeed uses Chromium with a sticky session
on the supplied Oxylabs proxy, UK locale/timezone, normal Chrome user-agent token,
automation compatibility flags and homepage warmup. Its public selected-job pane
provides full details; `vjk` selects listings. No accounts, CAPTCHA interactions/solving
services, other proxies or runtime LLM calls are used.

Indeed blocked HTTP, legacy headless rendering and browser-to-HTTP cookie handoff;
direct `viewjob` requests hit an anonymous auth gate. Browser traffic is heavier,
so HTTP sources run first. Images/fonts/media and bulky Indeed stylesheets are blocked.
Logo URLs come from source markup/branding JSON; banners and images are not stored.

Parsers verify IDs and UK eligibility, preserve source titles/locations, extract full
plain-text descriptions and exclude Reed training adverts. Missing fields stay null.
Contract/temporary takes precedence over hours; permanent alone does not imply full-time.
Relative posting dates are estimated once; exact source dates take precedence.

## Reconciliation and dedupe

Transactional writes preserve first seen, advance sightings, hash content edits, and
refresh details every 24 hours, including jobs absent from search. Failures remain due.
Only explicit expiry or confirmed source not-found removes a row; search absence,
incomplete runs and inline endpoint errors do not. Reappearance clears removal.

Dedupe indexes employer/role/location buckets, then checks requisitions, title
compatibility and distinctive descriptions after removing boilerplate. Conflicting
workplaces, teams, references, seniority or specialization reject links. Complete-link
checks prevent weak transitive merges. The oldest canonical ID survives merges;
wording edits preserve identity, while clear contradictions split the edited row.
Unknown employers and same-board copies without requisition evidence stay separate.
Versioned features/evidence do not affect content hashes or lifecycle counts.

Defaults: one page/query, ten details/source, 300 requests and ten minutes; configure
`CRAWL_QUERIES`, `CRAWL_MAX_*` and `DETAIL_REFRESH_HOURS`. Limits report partial coverage.
All boards work and a live cross-board duplicate is verified; broader review and
browser/volume optimization remain upcoming.

Each run rewrites `output/jobs.jsonl` (including removed rows) and `output/report.json`.
Source totals are live database counts; lifecycle counts are per-run. `duplicates_linked`
counts copies beyond one per stored canonical group. Logs are under ignored `output/runs/`.
Set `PROXY_COST_PER_GB_USD` for cost/1,000 request attempts; costs remain null without
the rate. Decoded bytes estimate traffic, not proxy billing. Export verification:
`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`.
