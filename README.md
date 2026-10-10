# Rotto UK job crawler

Python crawler for public, logged-out Indeed UK, LinkedIn and Reed listings. Requires Docker Compose and Make; the pinned image supplies Python and Chromium.

## Run

Supply `PROXY_URL` or `PROXY_HOST` / `PROXY_PORT` / `PROXY_USERNAME` / `PROXY_PASSWORD` through the environment or ignored `.env` (see `.env.example`).

```sh
docker compose up -d
make crawl
make test
FIXTURE_PATH=/path/to/file.json make test
```

`make crawl` builds the runtime and initializes schema. Postgres uses a persistent volume/local port `55432`; configure `POSTGRES_*` before first startup. Tests use the built image offline, check fixture rows/counts/replays in fresh UUID-named databases, and drop only those databases.

## Access, extraction and coverage

LinkedIn/Reed use Chrome-impersonated HTTP. Indeed uses Chromium, sticky supplied proxy, UK locale/timezone, native Chrome token, automation compatibility and homepage warmup. Public `vjk` search panes provide details. HTTP-only/legacy headless/cookie handoff failed; direct `viewjob` and page two hit auth gates. No accounts, CAPTCHA solving, other proxies or runtime LLM calls.

Indeed's lean policy skips frontend/consent/telemetry and images/fonts/media, retaining security checks. Every dispatched request/redirect/retry is logged; local skips are not attempts. Logo URLs are never downloaded. Parsers bind IDs to actual details, require UK workplace/remote eligibility, reject explicit overseas relocation/training adverts, preserve source titles/locations, and extract plain-text main descriptions. Dedicated compensation overrides conflicting prose; missing fields/periods are not guessed. Exact dates override stable relative estimates; bound Indeed discovery dates survive pane omissions.

Defaults: software/data queries, two HTTP pages/one Indeed page, 20 details/source, two-second HTTP pacing, 300 requests/ten minutes. Configure `CRAWL_QUERIES`, `CRAWL_LOCATIONS`, `CRAWL_MAX_*`, `INDEED_MAX_PAGES`, `DETAIL_REFRESH_HOURS`. LinkedIn uses guest offsets; Reed follows next links. Repeated pages/loops stop; overlaps fetch once. `CRAWL_DISCOVERY=auto` drains sufficient backlog, `always` rechecks heads, `never` drains queued/due work.

## Persistence, recovery and dedupe

Transactions preserve first seen, advance real sightings, hash content edits and refresh details every 24 hours—including search-absent jobs. Failures remain due. Pending IDs/dates/checkpoints survive interruption; observations/checkpoints and detail acknowledgements commit atomically. Cached work is not a sighting. `CRAWL_REFRESH_IDS=source:id,...` targets maintenance; `CRAWL_FORCE_REFRESH=1` bypasses freshness.

Only explicit expiry or confirmed not-found sets `removed_at`; search absence/failures do not. Reappearance clears removal. Invalid-import repair retains the full snapshot in quarantine rather than claiming source expiry.

Dedupe indexes employer/role/place and checks requisitions/distinctive text/contradictions. Complete-link checks avoid transitive false merges; oldest IDs survive and wording edits retain identity. Verified references are separate hash-bound provenance. Tesco channels require corroborated legal employer/requisition and exact role/place/text. Unknown aliases stay unlinked. Curated/holdout tests are not general precision/recall estimates.

## Outputs and cost

Every run rewrites `output/jobs.jsonl` (all assessment rows, including removed) and `output/report.json`. Source totals are live DB counts; lifecycle counts are per-run. Logs/captures are under ignored `output/runs/`. A 75-detail queue benchmark took 173 seconds and 114 requests, receiving 45.7 MB decoded bodies. This is approximately **0.61 × R USD per 1,000 listing fetches**, if actual proxy rate **R USD/GB** is supplied as `PROXY_COST_PER_GB_USD`; estimates otherwise remain null. Decoded bodies are not billed bytes. Reports separate listing fetches, network attempts, accepted refreshes/new jobs and per-source efficiency.

Verify DB/export/hash/request accounting with `docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`.
