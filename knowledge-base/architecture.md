# Architecture and interfaces

## Runtime

- `compose.yaml`: Postgres plus an opt-in crawler profile; `docker compose up -d`
  starts Postgres. Crawler mounts only `output/` and receives configuration through env.
- `Dockerfile`: digest-pinned Playwright image, pinned uv/dependencies, Python 3.12.
  Xvfb wrapper is available; production Indeed uses headless Chromium.
- `.dockerignore` excludes `.env*`, assessment text, VCS, local environments and outputs.
- `Makefile`: `make crawl` builds/runs the crawler; `make test` runs local-only test
  data inside fresh temporary databases; alternate fixtures mount read-only.

## Modules

- `crawler/run.py`: orchestration, discovery tasks, scheduled detail refresh and counters.
- `crawler/progress.py`: durable pending candidates, sanitized per-scope traversal
  checkpoints, matching-cycle resume and queue acknowledgement/scheduling.
- `crawler/fetching.py`: HTTP attempts, bounded retry/backoff, request logging and budgets.
- `crawler/browser_transport.py`: persistent Indeed browser session and public inline detail URLs.
- `crawler/browser_policy.py`: lean allow/skip policy retaining security-check resources.
- `crawler/browser_probe.py`: bounded diagnostics, durable request ledger and browser metadata capture.
- `crawler/parsers.py`: source identity, discovery, full-detail extraction, country/salary/text rules.
- `crawler/discovery_evidence.py`: offline captured-page inspection of result IDs,
  next links and location controls; performs no network requests.
- `crawler/indeed.py`: explicit pane ID, selected-view payload and public branding JSON extraction.
- `crawler/models.py`: normalized listings/observations, timezone validation and content hashes.
- `crawler/reconcile.py`: shared transactional persistence used by live crawl and offline fixtures.
- `crawler/dedupe.py`: indexed matching features, contradictions, complete-link canonical grouping.
- `crawler/matching_evidence.py`: verified current-page structured employer-reference extraction.
- `crawler/dedupe_review.py`: offline real-pair snapshot freezing/evaluation; no board requests.
- `crawler/metrics.py`: explicit per-source/global throughput, decoded traffic and cost units.
- `crawler/quarantine.py`: source-evidenced invalid-import repair preserving the full
  snapshot separately; not ordinary expiry/removal or a database reset.
- `crawler/exporting.py`: consistent snapshot, atomic files and matching jobs checksum.
- `crawler/verify_exports.py`: offline DB/export/request-log validation.
- `crawler/accuracy_review.py`, `browser_metrics.py`, `inspect_indeed.py`: local evidence/debug tools.

## Persistence

Jobs use `{source}:{source_job_id}` identity and all assessment columns. Rows are never
wiped/deleted during ordinary crawling. An explicit, identity/content-evidenced invalid
overseas import can be archived in `listing_quarantine` and excluded from assessment jobs
without falsely marking source expiry. Lifecycle timestamps, canonical IDs and refresh bookkeeping
are excluded from the SHA-256 source-content hash.

Supporting tables: `listing_state` (successful refresh time), `listing_exclusions`
(temporary validity rejection cache), `canonical_groups` (stable creation order),
`dedupe_features` (versioned indexed profiles) and `dedupe_evidence` (pair/hash/reason).

`listing_match_evidence` stores a current-content-hash-bound source reference/issuer
outside exported listing content. Listings/observations carry optional matching evidence;
reconciliation stores it in the same transaction as content and canonical changes.
Features include evidence fingerprints and a legal-employer candidate index. Metadata
changes invalidate grouping caches; changed-content snapshots cannot use stale evidence.

`pending_candidates` retains source IDs/public URLs, exact discovery-date hints,
discovery timestamps, attempted scheduling and reappearance refresh requirements.
It does not contain complete listings. `crawl_progress` stores each source's current
plan hash/cycle and completion/auth-limit state; `discovery_checkpoints` stores each
scope's next page/URL, observed ID set, page fingerprints and visited URLs. Matching
unfinished cycles resume within the configured refresh interval. Completed cycles
and changed/older plans restart search heads without discarding pending candidates.

Discovery sightings, queued IDs and checkpoints commit in one transaction. Detail
reconciliation and queue acknowledgement commit together. Failed details retain
pending work. Replaying a queue/checkpoint alone does not call discovery reconciliation.
Due stored refreshes precede queued work; queued known incompleteness/reappearance
precedes unknown IDs, with oldest unattempted/retry work first within each class.

Reconciliation serializes transactions with an advisory lock. Live orchestration uses
a separate session lock against overlapping runs. Tests create and remove only a new
`rotto_test_<uuid>` database; fixture `observed_at` controls time and each run is replayed.

## Outputs and evidence

- Intended exports: `output/jobs.jsonl`, `output/report.json`; include removed rows.
- Ignored evidence: `output/runs/`, `output/diagnostics/`, `output/reviews/`.
- Source counts are live DB totals; lifecycle counts are per-run. `duplicates_linked`
  is copies beyond one per stored canonical group; live canonical count is separate.
- Browser start/completion/skip events are durable. Routed requests reserve a network
  slot only at dispatch. Automatic redirects are still logged.
- HTTP starts/completions are also durable in `request-events.jsonl`. Handled in-flight
  interruptions finalize an `Interrupted` request record; source progress remains in
  reports when a crawl raises a budget/interrupt exception.
