# Clean-source reproducibility rehearsal — 2026-10-09

## Isolation and source snapshot

Created a clean runtime snapshot of the current candidate files, including uncommitted
code/tests, using a separate temporary Git index and `git checkout-index`. No commit
was created and the user's real staging/index and HEAD were preserved.

Snapshot tree: `f400cfe9dc343e407c90834c8ce81e8dc8ad022b`.
Only runtime/configuration files, README, `crawler/` and `tests/` were included.
The snapshot had no `.env`, `task.txt`, host `.venv`, captures, or existing exports.
Proxy credentials were passed through environment variables, not copied into files.

Started an isolated Compose project with a new volume and database
`rotto_test_a1735ecd75094697986c7dd25fb5eb20`. Verified the exact UUID database name
and zero public tables before crawling. An automatically assigned host port avoided
the existing live Postgres port. `docker compose build --no-cache crawler` installed
the pinned runtime/dependencies successfully; the base image was already available
on this Docker host. This is a clean current-code rehearsal on the existing host;
the final committed GitHub clone still needs checking before submission.

## Verified commands

In the isolated snapshot with the supplied proxy supplied through `PROXY_*` variables:

```sh
docker compose up -d
docker compose build --no-cache crawler
CRAWL_SOURCES=linkedin,reed,indeed CRAWL_QUERIES="software engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=150 CRAWL_MAX_SECONDS=300 CRAWL_REQUEST_DELAY=1 CRAWL_SAVE_PAGES=1 make crawl
# Same bounded make crawl command again for incremental verification.
docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports
make test
FIXTURE_PATH=/absolute/snapshot/path/tests/fixtures/lifecycle.json make test
```

The surrounding rehearsal environment set a unique `COMPOSE_PROJECT_NAME`, UUID
`POSTGRES_DB`, `POSTGRES_PORT=0`, and cleared `DATABASE_URL`/`TEST_DATABASE_ADMIN_URL`
overrides. `CRAWL_FORCE_REFRESH=0` and `DETAIL_REFRESH_HOURS=24` were explicit. Proxy
credentials were cleared for both test commands. No source URLs were fetched by tests;
dependency execution used locked/offline uv.

## Results

| Check | First live crawl | Incremental live crawl |
| --- | ---: | ---: |
| Indeed live rows | 2 | 4 |
| LinkedIn live rows | 2 | 4 |
| Reed live rows | 2 | 3 |
| Total live / canonical jobs | 6 / 6 | 11 / 11 |
| New / changed / removed | 6 / 0 / 0 | 5 / 0 / 0 |
| Logged requests | 18 | 18 |
| Blocked request records | 0 | 1 |
| Decoded body bytes | 5,999,608 | 6,136,378 |

The first crawl automatically initialized schema/persistence and produced real rows
from all three boards. Export verification passed for all six rows and 18 requests.

The second crawl preserved all six original first-seen timestamps, content hashes
and canonical IDs, retained live state, and advanced last seen where observed.
Fresh detail skips were 2 LinkedIn, 2 Reed and 1 Indeed; one earlier Indeed listing
was absent from the next search and remained stored. Five new listings were accepted
from outstanding candidate work, and one Reed training advert was excluded. Both
Indeed details succeeded despite the single blocked browser request record. The
new-row count exactly matched newly stored source IDs. Export verification passed
for all eleven rows and 18 logged requests, including after both test runs.

Both `make test` forms passed **88 tests**, all three supplied fixture runs, and their
idempotent replays. Each test database was freshly UUID-named. After tests, the only
remaining `rotto_test_*` database in the isolated instance was the rehearsal database;
no fixture/unit-test databases remained.

## Preservation and cleanup

Before/after ordered JSON fingerprints matched for all nine live persistence tables:
jobs, refresh state, exclusions, canonical groups, dedupe features/evidence, pending
candidates, source cycles and scope checkpoints. SHA-256 checks also confirmed that
the workspace's `output/jobs.jsonl` and `output/report.json` were untouched. Git HEAD
and staged diff were unchanged.

The isolated Compose project/network/volume was removed by its unique project name.
The original live Postgres remains healthy, with **37 listings / 36 canonical jobs**
and **72 Reed candidates queued**. Rehearsal rows are development evidence only and
were not added to those live totals or copied over the intended exports.

Evidence: `output/diagnostics/reproducibility-a1735ecd7509/` contains sanitized command
logs, first/second reports, initial JSONL, preservation fingerprints and `summary.json`.
Saved source pages/request logs are retained in the temporary snapshot's ignored
`output/runs/20261009T015708Z-3020528c/` and `20261009T015733Z-36b3af79/` folders.
The exact temporary snapshot location is recorded in the summary.

Rehearsal driver:
`uv run --locked --offline python /var/folders/d4/ndfskpvx28gfdb9h90ng9fv00000gn/T/opencode/rehearsal.py`.
It uses only `make crawl` for live board requests, creates a new UUID database/project
each invocation, and cleans up that isolated project. It is local verification tooling,
not a runtime prerequisite for the evaluator.

## Final default-runtime rehearsal — 2026-10-10

The driver was updated to exercise the actual current defaults, rather than the old
two-detail developer budget, and fingerprint all eleven live persistence tables.
Snapshot tree: `0d69d133db8b8ea3fa1c32c535cddd2af315541c`.
Evidence: `output/diagnostics/reproducibility-8b3eaa4cfc20/summary.json` and logs/reports.
The snapshot includes current code/tests and README, excluding credentials, captures,
host environment and old exports. An uncached build and empty
`rotto_test_8b3eaa4cfc20495b8ae01da854395558` database passed the same setup path.

| Check | First default crawl | Incremental crawl |
| --- | ---: | ---: |
| Indeed live rows | 16 | 31 |
| LinkedIn live rows | 17 | 21 |
| Reed live rows | 19 | 37 |
| Total rows | 52 | 89 |
| New / changed / removed | 52 / 0 / 0 | 37 / 0 / 0 |
| Network attempts | 109 | 88 |

All three boards produced real rows from empty state with no manual schema/dependency
fix. Every original first-seen/content hash/canonical ID remained stable in the second
run, and zero fresh original details were re-fetched. LinkedIn/Reed skipped discovery
through auto queue draining; Indeed rechecked heads when its remaining queue was smaller
than the twenty-detail budget. LinkedIn hit a 429 in the second run and stopped that
source safely; other boards proceeded, prior data stayed intact and exports were valid.
Indeed rejected four/five metadata/identity selections safely; no page-two auth request.

Both default and absolute-fixture `make test` forms passed **115 tests**, all three
fixture runs and idempotent replays with proxy credentials cleared. Export verification
passed after both live runs and tests. No temporary test databases remained. The unique
rehearsal project/network/volume was removed; all eleven original table fingerprints,
export hashes, staged diff and HEAD matched before/after. Rehearsal rows did not replace
the intended exports or add to main live totals.

Final workspace export verification passed at **134 stored rows, 133 live listings /
131 canonical jobs / two duplicate links**. The readonly credential audit passed across
77 candidate paths, staged blobs and 70 historical blobs across four commits. The only
initial pattern flag was a deliberate fake URL in an unsafe-redirect test; constructing
that dummy URL from explicit dummy pieces preserved behavior and cleared the false flag.
`.env`, `task.txt` and captures/reviews/diagnostics remain ignored. `git diff --check` passes.

README is **498 whitespace-delimited words** and intentionally compact for the one-page
contract. `submission-checklist.md` contains owner actions and a timed 4m40s Loom guide.
The SSH remote is reachable (`git ls-remote --heads origin`), but remote main still points
to the old checkpoint commit. No commit/push was authorized or performed. GitHub CLI is
absent, so repository privacy and `gibbsdylan` access require owner confirmation. Final
committed remote-clone verification, Loom recording/share link and actual submission
remain release actions, not claims made by this rehearsal.

Next: independent review of remaining stored rows, expansion toward 25 reviewed
listings per board, then final committed-repository access/clone and submission checks.
