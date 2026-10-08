# Implementation plan

## Goal and priorities

Build a reproducible Python crawler for Indeed UK, LinkedIn Jobs, and Reed that stores accurate UK listings in Postgres and reconciles them correctly across repeated runs.

**Deadline:** Saturday, October 10, 2026, at 6:12 PM EDT. Reserve the final working block for clean-machine verification, exports, documentation, and the Loom.

Prioritize a working integration for every board, extraction accuracy, lifecycle correctness, and failure handling before maximizing volume. Accuracy is worth 25 points, reconciliation 20, failure handling 15, deduplication 15, reproducibility 10, volume 5, efficiency 5, and explanation 5. Volume earns points only for boards with at least 90% sampled accuracy and has diminishing returns.

## Constraints and deliverable contract

- Public, logged-out pages only; no accounts or CAPTCHA-solving services.
- Use the supplied UK residential proxy or direct access; no other proxies or paid infrastructure.
- Read credentials from `PROXY_URL` or `PROXY_HOST` / `PROXY_USERNAME` / `PROXY_PASSWORD`; support the supplied port through configuration. Never embed credentials in code or logs.
- Python crawler and parser; no runtime LLM calls.
- `docker compose up -d` starts Postgres; `make crawl` is the only live crawl command and performs setup, crawling, reconciliation, and exports without interactive steps.
- `make test` runs offline against a separate empty test database, using the same persistence code as the live crawl. Support `FIXTURE_PATH=/path/to/file.json make test`.
- Every required jobs-table column must exist. Exports contain the same fields, including explicit nulls, and all stored rows, including removed listings.
- Rewrite `output/jobs.jsonl` and `output/report.json` on every run; commit the latest real-run exports for submission.
- README: at most one page. Loom: at most five minutes. Private repository shared with `gibbsdylan`.

## Phase 1 — Resolve inputs and prove live access

- [x] Obtain the supplied version-1 lifecycle fixture and save it at `tests/fixtures/lifecycle.json`; its synthetic URLs must never be fetched.
- [x] Confirm local Python, Docker, and dependency tooling and choose a simple pinned setup.
- [x] Configure proxy credentials locally through environment variables. Ignore local credential files and keep the credential-bearing assessment text out of tracked files.
- [x] Establish request logging before live probes, so exploration traffic is included in our bandwidth accounting.
- [ ] Through a small diagnostic run, retrieve a discovery page and at least one full listing from each board. Route live board probes through `make crawl` with a bounded configuration.
- [ ] Identify stable source IDs, public URLs, pagination behaviour, UK-location evidence, full-description availability, and any reliable content-change signals.
- [ ] Inspect public HTML, embedded structured data, and any public logged-out endpoints used by the pages. Verify actual fields rather than assuming an endpoint or parser will work.
- [ ] Start with lightweight HTTP fetching; evaluate browser fetching only where observed access or rendering requires it. Record successful approaches, failed attempts, request counts, and bytes.
- [ ] Determine how proxy charging works. The brief supplies an allowance but no USD rate; document any cost-rate assumption instead of presenting an unsupported exact cost.

**Acceptance:** a documented access path and accurate full-description extraction example for each board, or a concrete blocker with logs and a next experiment. Keep probes small; do not start broad crawling before this gate.

**Initial findings:** see `access-findings.md`. LinkedIn and Reed discovery/detail pages were accessible in small HTTP probes; Indeed returned a managed JavaScript challenge. The lifecycle fixture is now available. The browser experiment encountered a local filesystem permission error and needs recovery and verification.

## Phase 2 — Persistence contract and offline lifecycle tests

- [x] Define a normalized listing model containing every required schema field and validation rules. Separate extracted content from database-owned lifecycle metadata.
- [x] Create the Postgres schema with repeatable initialization. Enforce `{source}:{source_job_id}` identity and allowed source values.
- [x] Define explicit reconciliation inputs: observed listings, content observations versus discovery-only sightings, and confirmed removals. Adapt the actual fixture format into these inputs; traversal completion alone never supplies removal evidence.
- [x] Implement transactional source-ID inserts/updates and per-run counters using persisted previous state.
- [x] Keep successful detail-refresh timestamps outside the content hash in a supporting table.
- [ ] Add source change signals and crawl-resumption state when integrating live fetching.
- [x] Build the fixture runner using the same reconciliation service, with assertions against expected stored rows and report counts after every run. Apply each run a second time, compare the complete stored rows before/after replay, and require zero lifecycle counts.
- [x] Guarantee test-database isolation: create a new uniquely named database, verify its name, and remove only the database created by that session. Never reset a configured existing database.
- [x] Exercise unseen listings, unchanged observations, edited content, detail-only changes, explicit removal, repeat removal, reappearance, partial runs, failed pages, and repeated identical input. Add focused tests where the supplied fixture leaves important cases uncovered.

### Lifecycle invariants

| Event | Required result |
| --- | --- |
| New valid source ID | Insert once; set first/last seen; increment `jobs_new` |
| Existing listing observed | Advance last seen; preserve first seen |
| Existing content changes | Update content/hash; increment `jobs_changed` |
| No content change | Preserve content/hash; no changed count |
| Confirmed live-to-removed transition | Set removed timestamp; retain row; increment `jobs_removed` |
| Already removed, removal confirmed again | Preserve removal state; no new removal count |
| Same source ID reappears | Clear removal; preserve original first seen; refresh last seen/content |
| Search absence, blocked page, failed pagination, interrupted run | Preserve good data; no absence-based removal |
| Proven complete authoritative scope excludes a listing | Permit removal only within that exact scope |

Use deterministic hashes over normalized source content. Exclude observation times, refresh bookkeeping, and dedupe assignments. Stabilize estimated relative posting dates so the passage of time alone does not manufacture content changes; document the estimation policy.

Do not overwrite complete records with partial search-card data. A discovery sighting can advance observation metadata without pretending that the full description has been refreshed.

**Acceptance:** default and alternate fixtures pass offline in an isolated database; lifecycle counts reflect transitions within the current run rather than database totals. Confirm the fixture's precise counting semantics before finalizing the runner.

**Verified:** `docker compose up -d` starts healthy Postgres 17 with a persistent volume on local port `55432` (the usual `5432` was occupied). `make db-init`, `make test`, and the absolute-path `FIXTURE_PATH` variant pass. All three public fixture runs and replays plus eight additional lifecycle tests pass. The live jobs table remains empty after tests and no temporary test databases remain. Live-adapter integration is the next milestone.

### Confirmed version-1 fixture contract

- Use each run's `observed_at` as the clock, never the actual test execution time.
- `discovered_source_job_ids` are live sightings. Existing rows advance `last_seen_at` even without successful detail fetches; preserve their complete content and hash.
- `details` contains successful normalized detail observations. New rows require sufficient detail data; discovery alone must not manufacture incomplete job records.
- `failed_detail_source_job_ids` must not erase stored content or be interpreted as removals.
- `discovery_complete` reports traversal completion. It does not authorize removal; only `confirmed_removed_source_job_ids` supplies removal evidence in this fixture interface.
- `expected.rows` is the exact set of row IDs, with assertions for the supplied fields. Reject both missing and unexpected rows.
- `content_hash_equals_run` references the same row's saved hash after the named prior run. Null denotes new content; check new/edited hashes appropriately without inventing expected algorithm-specific hash strings.
- Every run is applied twice. The second application must leave all stored row values unchanged, including hashes, canonical IDs, and timestamps, and return zero `jobs_new`, `jobs_changed`, and `jobs_removed` counts.
- The sample covers initial inserts, discovery-only updates plus a new job, and a detail edit. Add separate meaningful cases for failed details, partial discovery, removal, and reappearance; the public sample does not exercise these.
- Canonical IDs and hashing are implementation choices. Do not hard-code fixture IDs, names, content, timestamps, or expected counts into persistence logic.

## Phase 3 — Shared fetching and operational behaviour

- [x] Separate HTTP fetching, source parsing, reconciliation, and export/reporting into understandable modules. Source adapters reuse the same infrastructure; deduplication remains a separate upcoming module.
- [x] Log every HTTP request attempt, including retries and redirects. Record source, time, URL, status/error, duration, received bytes, retry index, and block classification without credentials.
- [ ] Recover browser diagnostics with durable request logging before using them in the production pipeline.
- [x] Detect challenge pages, including HTTP 200 responses that contain bot protection instead of listings. Do not count these as successful extraction or removal evidence.
- [x] Implement timeouts, bounded retries, backoff with jitter, sequential rate-limited requests, and stopping the affected source after a block.
- [x] Persist successful observations so reruns skip fresh details and resume missing work safely. Use idempotent writes rather than a wipe-and-reload workflow.
- [x] Prevent overlapping crawl processes from producing conflicting lifecycle changes or exports.
- [x] Finalize reports and exports on handled partial failures and interrupts; preserve committed data after abrupt termination and make the next run recover safely.
- [x] Aggregate request totals, blocked totals, statuses/errors, decoded response-body bytes, and estimated cost consistently with request logs. Costs remain null until the actual rate is supplied.

**Acceptance:** a blocked source or failed page leaves existing data intact, retries terminate, and request/report statistics explain what happened.

## Phase 4 — Accurate end-to-end adapters for all three boards

**Working subset:** LinkedIn and Reed now persist live UK listings via `make crawl`, including full descriptions and source-served company logo URLs. Indeed is attempted and reported as blocked; its detail parser is unverified. Full three-board acceptance remains open.

- [ ] Implement the smallest complete discovery-to-detail-to-database path for each board, using Phase 1 findings.
- [ ] Extract board-owned source IDs and stable public URLs; avoid using titles or URL slugs as listing identity.
- [ ] Validate UK workplaces or explicit UK remote eligibility. Use source evidence, not the domain or the word “remote” alone; skip ambiguous eligibility initially.
- [ ] Extract title, company, source-served hiring-company logo URL, original location text, work type, salary range/period, posting date, and full plain-text description.
- [ ] Preserve useful description structure while removing HTML, navigation, recommendations, and unrelated page text. Do not download logos.
- [ ] Store null for genuinely unavailable optional data. Handle ranges, single-value salaries, and relative posting dates using documented source-specific rules; do not guess missing values.
- [ ] Validate live state. Treat explicit expiry or confirmed source not-found as removal evidence only after ruling out challenges and transient/access errors.
- [x] Add compact parser regression samples modeled on observed LinkedIn/Reed markup and focused tests for identity, description boundaries, eligibility, salaries, and block/expiry detection.
- [ ] Expand parser samples and manual review across more layouts and the Indeed integration.
- [ ] Manually compare a small sample from each board field by field with public pages, expanding checks as volume grows. Aim for at least 95% accuracy.

**Acceptance:** one `make crawl` produces independently verifiable live UK listings from all three sources, with full descriptions and every required field present.

**Verified live milestone:** a nine-request bounded run inserted three LinkedIn and two Reed listings and excluded a Reed training course; Indeed returned HTTP 403. A three-request discovery-only rerun preserved all five first-seen timestamps and content hashes, advanced last seen, and returned zero lifecycle counts. Both runs exported real stored rows, and the export verifier checked table equality, hashes, source counts, and request-log accounting.

## Phase 5 — Incremental refresh and careful deduplication

- [ ] Store discovery signals and last successful detail-refresh time separately. Use a source change signal only after verifying it actually represents relevant content changes.
- [ ] Fetch details for new listings, changed reliable signals, and due periodic refreshes. Define concrete per-source intervals based on observed signals and traffic budget.
- [x] Without a verified full-content change signal, refresh details every 24 hours by default, oldest due first within run budgets, including stored listings absent from current search results.
- [x] A failed refresh must remain due; never advance successful-refresh timestamps on failed or blocked requests.
- [x] Revalidate liveness during detail refreshes; require explicit expiry or two matching source not-found responses. Never remove based on search absence.
- [ ] Generate plausible duplicate candidates using normalized company/title/location and other available evidence; use description similarity and distinctive attributes to confirm matches.
- [ ] Choose conservative matching thresholds; account for generic titles, staffing agencies, different locations, and multiple similar vacancies.
- [ ] Persist stable canonical IDs across reruns. Define how edited listings and new evidence affect existing groups without indiscriminate churn or weak transitive merges.
- [ ] Evaluate labeled positive and negative pairs, including duplicates the algorithm initially misses. Avoid all-pairs comparisons as the dataset grows.
- [ ] Define and document `duplicates_linked` precisely, since the brief does not specify whether it is a run-transition count or a current grouping count. Follow the supplied fixture if it clarifies this.

**Acceptance:** unchanged listings avoid unnecessary details, a detail-only edit is detected when refresh becomes due, failed refreshes do not hide changes, and true duplicates share a stable canonical ID without merging distinct vacancies.

## Phase 6 — Scale coverage within the budget

- [ ] Broaden discovery using source-supported pagination and nonredundant UK query partitions selected from observed source limits.
- [ ] Detect repeated pages, pagination loops, result caps, overlapping queries, and unstable result ordering. Never label capped search coverage as authoritative completeness.
- [ ] Avoid redundant detail requests across overlapping queries and already-fresh listings.
- [ ] Tune per-source concurrency from measured success/block rates, valid jobs per request, bytes per job, and remaining allowance.
- [ ] Track distinct live source listings and distinct canonical jobs separately. Keep all three boards represented.
- [ ] Use configurable limits and time budgets for development, then select a practical documented default that runs unattended on the evaluator's clean machine.
- [ ] Stop or back off wasteful blocked traffic. Request additional allowance only if progress and measurements justify it.
- [ ] Recheck accuracy as discovery expands; scale only adapters that remain reliable.

**Acceptance:** increased verified coverage without sacrificing correctness, bounded unattended execution, and measurable request/bandwidth efficiency.

## Phase 7 — Reproducibility and submission

- [ ] Verify clean setup: `docker compose up -d`, then `make crawl`, with dependencies/schema initialization handled automatically and credentials supplied only through the supported environment interface.
- [ ] Run `make crawl` again and verify first-seen preservation, correct counts, persistence, and reduced unnecessary detail requests.
- [ ] Run `make test` and `FIXTURE_PATH=/path/to/file.json make test` with no network/proxy access.
- [x] Export all rows with explicit nulls, valid JSONL, consistent timestamps, and deterministic ordering. Publish each file atomically and include an export checksum to identify the matching report snapshot.
- [x] Verify `output/report.json` contains `started_at`, `finished_at`, `requests_total`, `requests_blocked`, `requests_by_status`, `jobs_by_source`, `duplicates_linked`, `jobs_new`, `jobs_removed`, `jobs_changed`, and `estimated_cost_usd`.
- [x] Source counts represent live database totals; lifecycle counts are strictly per-run. Include source outcomes and configured limits as partial-run context.
- [ ] Write the one-page README: setup, architecture, access methods and failed attempts, refresh/removal policy, dedupe tradeoffs, and cost per 1,000 pages with assumptions.
- [ ] Record the Loom: demonstrate a real crawl and explain access, reconciliation, safe removals, dedupe, and efficiency decisions in under five minutes.
- [ ] Review tracked files for credentials; commit the latest real exports and intended code changes when ready to submit.
- [ ] Confirm private repository access for `gibbsdylan`, push before the deadline, and submit repository and Loom links through the assessment form.

**Acceptance:** the evaluator can reproduce the live crawl and offline tests without manual code changes, and the committed exports are substantiated by actual runs.

## Immediate next work session

1. Recover and verify the interrupted Indeed browser experiment, with durable request logging, and complete three-board live coverage.
2. Broaden field-by-field review and parser samples, then implement measured cross-board deduplication.
3. Investigate reliable source change signals and add richer pagination/resumption bookkeeping as discovery scales.
4. Expand queries and paging within measured accuracy and bandwidth limits, then complete clean-machine setup verification and submission materials.

Keep evidence of access experiments and unresolved decisions as implementation progresses. Finalize source-specific details from observed behaviour rather than assumptions.
