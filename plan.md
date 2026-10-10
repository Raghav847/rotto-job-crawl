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

**Findings:** see `access-findings.md`. All three integrations have now produced real listings. Indeed access required Chromium, sticky proxy sessions, normal browser identity, homepage warmup and public embedded job panes. The repaired asynchronous diagnostic has durable logs, and the Docker runtime avoids the earlier native-browser filesystem failure. The supplied lifecycle fixture is integrated.

## Phase 2 — Persistence contract and offline lifecycle tests

- [x] Define a normalized listing model containing every required schema field and validation rules. Separate extracted content from database-owned lifecycle metadata.
- [x] Create the Postgres schema with repeatable initialization. Enforce `{source}:{source_job_id}` identity and allowed source values.
- [x] Define explicit reconciliation inputs: observed listings, content observations versus discovery-only sightings, and confirmed removals. Adapt the actual fixture format into these inputs; traversal completion alone never supplies removal evidence.
- [x] Implement transactional source-ID inserts/updates and per-run counters using persisted previous state.
- [x] Keep successful detail-refresh timestamps outside the content hash in a supporting table.
- [x] Add durable pending candidates and scope/cycle checkpoints for crawl resumption. No reliable full-content change signal is assumed; periodic refresh remains necessary.
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
- [x] Repair browser diagnostics with durable request-start/completion logs and failure-safe cleanup; integrate browser request accounting into live reports.
- [x] Detect challenge pages, including HTTP 200 responses that contain bot protection instead of listings. Do not count these as successful extraction or removal evidence.
- [x] Implement timeouts, bounded retries, backoff with jitter, sequential rate-limited requests, and stopping the affected source after a block.
- [x] Persist successful observations so reruns skip fresh details and resume missing work safely. Use idempotent writes rather than a wipe-and-reload workflow.
- [x] Prevent overlapping crawl processes from producing conflicting lifecycle changes or exports.
- [x] Finalize reports and exports on handled partial failures and interrupts; preserve committed data after abrupt termination and make the next run recover safely.
- [x] Verify live process interruption/resumption: Reed page one/25 pending IDs committed
  before SIGINT; rerun resumed at page two in the same cycle and accepted two queued jobs.
  Offline tests also verify page/detail rollback and acknowledgement after interruption.
- [x] Aggregate request totals, blocked totals, statuses/errors, decoded response-body bytes, and estimated cost consistently with request logs. Costs remain null until the actual rate is supplied.

**Acceptance:** a blocked source or failed page leaves existing data intact, retries terminate, and request/report statistics explain what happened.

## Phase 4 — Accurate end-to-end adapters for all three boards

**Working coverage:** LinkedIn, Reed and Indeed persist live UK listings via `make crawl`. Indeed verifies the selected pane ID against source metadata, extracts only the full description, uses per-listing UK country evidence, and separates company logos from banners. Larger field-by-field sampling remains necessary before scaling.

- [x] Implement a verified small discovery-to-detail-to-database path for each board, using observed source behaviour.
- [ ] Extract board-owned source IDs and stable public URLs; avoid using titles or URL slugs as listing identity.
- [ ] Validate UK workplaces or explicit UK remote eligibility. Use source evidence, not the domain or the word “remote” alone; skip ambiguous eligibility initially.
- [ ] Extract title, company, source-served hiring-company logo URL, original location text, work type, salary range/period, posting date, and full plain-text description.
- [ ] Preserve useful description structure while removing HTML, navigation, recommendations, and unrelated page text. Do not download logos.
- [ ] Store null for genuinely unavailable optional data. Handle ranges, single-value salaries, and relative posting dates using documented source-specific rules; do not guess missing values.
- [ ] Validate live state. Treat explicit expiry or confirmed source not-found as removal evidence only after ruling out challenges and transient/access errors.
- [x] Add compact parser regression samples modeled on observed LinkedIn/Reed markup and focused tests for identity, description boundaries, eligibility, salaries, and block/expiry detection.
- [ ] Expand parser samples and manual review across more layouts and the Indeed integration.
- [ ] Manually compare a small sample from each board field by field with public pages, expanding checks as volume grows. Aim for at least 95% accuracy.

**Initial accuracy review:** see `accuracy-findings.md`. All 20 current rows have captured source evidence and were rechecked through fresh live detail observations. Five LinkedIn salary records and one inline-word formatting defect were corrected; Indeed's selected-view fallback now works when the job is absent from search cards. Larger random samples (at least 25 per board), additional layouts, real remote roles and hidden-employer cases remain open. The description word-stream check agrees for 20/20 rows but is not an accuracy score.

**Twelve-listing follow-up (2026-10-09):** four new listings per board were reviewed
against complete captured descriptions/metadata, bringing documented review coverage
to 32 rows (7 Indeed, 15 LinkedIn, 10 Reed). Four Indeed dates were missing because
the selected panes omitted dates present on earlier search cards. ID-bound candidate
date hints now survive scope changes and enrich only successful detail observations.
Two live maintenance runs corrected all four dates while preserving first seen and
canonical IDs; no new listings/removals. Other fields agree in this batch, including
hourly PAYE/umbrella source precedence and null Indeed branding logos. All 76 tests
plus lifecycle replays/export verification pass. Broader random sampling remains open.

**Remaining-five review (2026-10-09):** the DFYNE/Tesco/Kingdom People rows and two
new Reed data-engineer rows were reviewed against captured full descriptions and
source metadata. No additional extraction defects; all five word streams agree.
Documented source-field review now covers every current live row (8 Indeed, 16
LinkedIn, 13 Reed). FDM's returner listing is employment with upskilling, not a
tuition-only advert. A Tesco/Tesco Technology same-vacancy candidate with identical
text/place and shared reference stem was recorded for matching-policy review.
Export verification passes; the 25-reviewed/source and broader dedupe goals remain open.

**LinkedIn 25-reviewed milestone (2026-10-09):** a bounded two-page/12-detail crawl
added ten listings using 14 requests, no blocks, and two UK-ambiguous rejections.
All ten were reviewed field by field. Wise's contradictory `£145,000k`/`145K GBP`
wording revealed one parser defect; explicit GBP notation and narrow corroboration
now produce 111000/145000 with null period. A two-request targeted maintenance run
applied the correction, preserving first seen/canonical ID. All 93 tests/fixture
replays and export checks pass. Current source-field review covers 47 live rows:
8 Indeed, 26 LinkedIn, 13 Reed. Reed/Indeed still need 12/17 reviews respectively.

**Reed 25-reviewed milestone (2026-10-09):** a two-query/two-page/15-detail crawl
added fifteen listings using 19 requests, no blocks or failures. All fifteen full
descriptions and source fields were reviewed; no new extraction defect. Daily versus
annual compensation, absent logos, nonnumeric pay and source headline/prose differences
were checked. Three abrupt Norton Rose description endings agree across visible and
structured text, so no source continuation is invented. Concrete Norton Rose/Connells
negative dedupe examples were recorded. Review now covers 62 live rows: 8 Indeed,
26 LinkedIn, 28 Reed; exports verify with 61 canonical jobs. Indeed needs 17 further
reviewed listings for the third-board milestone.

**All-board 25-reviewed milestone (2026-10-09):** six public Indeed first-page
software/data UK/London/Manchester scopes added twenty valid listings from 22 detail
selections, with two identity failures safely excluded. 78 requests/33.84 MB decoded
bodies; no content changes/removals or page-two auth attempts. All twenty full
descriptions and source fields were reviewed with no new extraction defect; all
twenty ID-bound discovery dates match stored dates. Additional cases cover UK-eligible
remote/home working, full-time four-day weeks, one-sided salary ceilings, permanent-only
type nulls, declared logo versus banner, and headline/prose discrepancies. Current
reviewed counts are 28 Indeed, 26 LinkedIn and 28 Reed (82 live/81 canonical jobs).
All boards exceed 25 reviewed rows; general/random accuracy and real dedupe evaluation
remain open. See `accuracy-findings.md` for the full per-row evidence.

**Acceptance:** one `make crawl` produces independently verifiable live UK listings from all three sources, with full descriptions and every required field present.

**Verified live milestone:** a nine-request bounded run inserted three LinkedIn and two Reed listings and excluded a Reed training course; Indeed returned HTTP 403. A three-request discovery-only rerun preserved all five first-seen timestamps and content hashes, advanced last seen, and returned zero lifecycle counts. Both runs exported real stored rows, and the export verifier checked table equality, hashes, source counts, and request-log accounting.

**Three-board milestone:** the Docker/Chromium pipeline added Indeed listings, including Rolls-Royce and Leidos roles in Bristol. A subsequent all-board run accepted one new listing per board. The current database/export contains 3 Indeed, 7 LinkedIn and 6 Reed listings. A discovery-only rerun retained all 16 rows with zero new/changed/removed counts and no scheduled detail fetches. Public fixture checks and the expanded parser/browser/pipeline tests run inside the Python 3.12 container. Browser requests remain comparatively expensive; cache/discovery optimization is an upcoming efficiency task.

## Phase 5 — Incremental refresh and careful deduplication

- [ ] Store discovery signals and last successful detail-refresh time separately. Use a source change signal only after verifying it actually represents relevant content changes.
- [ ] Fetch details for new listings, changed reliable signals, and due periodic refreshes. Define concrete per-source intervals based on observed signals and traffic budget.
- [x] Without a verified full-content change signal, refresh details every 24 hours by default, oldest due first within run budgets, including stored listings absent from current search results.
- [x] A failed refresh must remain due; never advance successful-refresh timestamps on failed or blocked requests.
- [x] Revalidate liveness during detail refreshes; require explicit expiry or two matching source not-found responses. Never remove based on search absence.
- [x] Generate candidates using indexed normalized employer/role/location buckets; compare requisitions, title compatibility, and distinctive description tokens/shingles.
- [x] Choose conservative thresholds and reject conflicting references, workplaces/postcodes, named teams, seniority, specializations and explicit working hours. Reject unknown employers and unverified recruiter/employer aliases.
- [x] Preserve the oldest established canonical ID on merges, keep identity through wording-only edits, and split an edited listing on clear contradictions. Complete-link checks reject weak transitive bridges.
- [x] Evaluate 16 labelled synthetic positive/negative pairs and a manually reviewed live Leidos copy across Indeed/LinkedIn. Indexed candidates avoid global all-pairs comparisons.
- [x] Add a frozen independently inspected real-pair development corpus and measure its precision/recall. Continue expanding cross-board positives and independent holdout cases beyond its two current positives.
- [x] Define `duplicates_linked` as stored copies beyond one per canonical group; lifecycle counts remain per-run and exclude canonical-only changes.

**Acceptance:** unchanged listings avoid unnecessary details, a detail-only edit is detected when refresh becomes due, failed refreshes do not hide changes, and true duplicates share a stable canonical ID without merging distinct vacancies.

**Dedupe milestone:** shared persistence now builds versioned matching features and hashed match evidence transactionally. Legacy rows are indexed once without detail requests. The targeted Leidos crawl added four LinkedIn rows and linked the Bristol Software Engineer copy to its existing Indeed canonical ID; differing Leidos locations/roles stayed separate. The database contains 20 live source listings and 19 canonical jobs, with one duplicate link. A discovery-only replay returned zero lifecycle counts and retained the grouping. All 55 tests and the public fixture pass; synthetic pair precision/recall are perfect on this small labelled set, not a general accuracy claim.

**Real-corpus/reference milestone (2026-10-09):** sixteen labelled pairs from 26
source snapshots (two positives/fourteen negatives) are frozen for offline regression.
Baseline TP=1/FN=1/FP=0/TN=14; rule version 2 gives TP=2/FN=0/FP=0/TN=14 on this
small curated set. Identity-bound structured employer references are persisted outside
content hashes with evidence-cache invalidation. A narrowly corroborated Tesco channel
rule links the same legal employer/requisition/title/place/text without general aliases.
Three live requests refreshed the two existing Tesco rows and retained the older
canonical ID, original first seen/hashes and Leidos group, with zero lifecycle changes.
Exports verify at 82 live/80 canonical jobs/two duplicate links. All 102 tests and fixture
replays pass. Broader positives/independent holdout remain open; see `dedupe-findings.md`.

## Phase 6 — Scale coverage within the budget

**Efficiency milestone:** see `efficiency-findings.md`. For the same three-Indeed-detail review workload, the lean resource policy reduced request attempts from 224 to 24 and decoded bytes from 12.74 MB to 6.31 MB, with three successful refreshes and unchanged stored content. Security-check resources remain allowed. Locally skipped requests now reserve no network-budget slots; automatic redirects remain logged. Larger benchmark samples and document-traffic optimization are still needed.

**New-listing verification:** a subsequent all-board bounded run accepted one new job per board using 23 requests total. Current exports hold 23 live source rows (4 Indeed, 12 LinkedIn, 7 Reed), 22 canonical jobs and one linked duplicate. All 65 tests and the public lifecycle fixture pass; the export verifier matches table contents and request accounting.

- [x] Broaden discovery using source-supported pagination and nonredundant UK query partitions selected from observed source limits.
- [x] Detect repeated pages, pagination loops, configured page caps and overlapping queries. Never label capped search coverage as authoritative completeness; ordering instability remains an operational constraint.
- [x] Avoid redundant detail requests across overlapping queries and already-fresh listings.
- [ ] Tune per-source concurrency from measured success/block rates, valid jobs per request, bytes per job, and remaining allowance.
- [x] Add queue-aware discovery and a coordinated sequential benchmark with per-source
  request/traffic/block/accepted/new metrics. Preserve untested concurrency as optional
  later work rather than assuming it is faster under source blocking.
- [ ] Track distinct live source listings and distinct canonical jobs separately. Keep all three boards represented.
- [x] Select documented queue-aware defaults: software/data queries, two HTTP pages/one Indeed page, twenty details/source, two-second HTTP pacing, 300 requests/600 seconds.
- [ ] Stop or back off wasteful blocked traffic. Request additional allowance only if progress and measurements justify it.
- [ ] Recheck accuracy as discovery expands; scale only adapters that remain reliable.

**Acceptance:** increased verified coverage without sacrificing correctness, bounded unattended execution, and measurable request/bandwidth efficiency.

**Coordinated speed/quality pass (2026-10-09):** a 75-task all-board queue run finished
in 172.724 seconds, avoiding rediscovery on every board and using 114 requests/45.73 MB
decoded bytes. Independent triage plus seeded five/source full-text review caught two
defects missed by simple metadata agreement: an Australian relocation false positive
and copied-page footer/between-and salary. The incorrect import is fully archived with
source proof, not marked expired; one targeted request applied the description/salary
repair. Source-confirmed expiry remains separate. Current exports verify at 133 live/
131 canonical jobs, 134 stored rows plus one invalid snapshot archived. Defaults,
artefact filtering/queue suppression and explicit cost metrics are implemented; 115 tests
and fixture replays pass. A separate seven-negative/one-unresolved dedupe holdout passes
without claiming recall. 265 candidates remain queued and the cohort is sampled/triaged,
not wholly manually reviewed. See `acceleration-findings.md` for commands and limits.

**Discovery milestone (2026-10-09):** two queries across UK-wide/London scopes found
197 LinkedIn, 102 Reed and 56 Indeed IDs; a five-detail/source budget added four
listings per board (35 live rows/34 canonical jobs total) using 64 requests. Reed's
ignored location parameter was corrected to declared `-jobs-in-london` paths.
A three-page discovery-only follow-up found 208 LinkedIn, 266 Reed and 52 Indeed IDs
with 51 requests and zero lifecycle transitions. LinkedIn guest offsets 60/70 work,
but a subsequent scope returned 429; stop-on-block preserved data. Indeed's page-two
sign-in limit is learned once per run, allowing later public first-page scopes and
details. Export verification passed after both runs; 74 tests plus fixture replays
pass. Evidence/commands are in `knowledge-base/status.md`; larger accuracy sampling,
pending-candidate queues and durable traversal checkpoints remain open.

**Recovery milestone (2026-10-09):** durable candidate/date queues and source/scope
checkpoints now commit atomically with observations. Matching unfinished cycles resume
within the refresh interval; completed/changed/stale plans restart discovery while
retaining queued details. A live Reed SIGINT run retained 25 IDs and all 35 stored rows;
the rerun fetched pages two/three plus two queued details (four requests), producing
37 live rows/36 canonical jobs and leaving 72 candidates pending. Both export checks
passed. All 88 tests plus fixture runs/replays pass; full evidence is in
`recovery-findings.md` and the knowledge base. Fresh-checkout rehearsal remains next.

## Phase 7 — Reproducibility and submission

- [x] Verify clean current-code setup: `docker compose up -d`, then `make crawl`, with dependencies/schema initialization handled automatically and credentials supplied only through the supported environment interface. Final committed remote-clone verification remains a submission step.
- [x] Run `make crawl` again and verify first-seen/hash/canonical preservation, correct counts, persistence, and fresh-detail skips.
- [x] Run `make test` and `FIXTURE_PATH=/path/to/file.json make test` offline with proxy credentials cleared.
- [x] Export all rows with explicit nulls, valid JSONL, consistent timestamps, and deterministic ordering. Publish each file atomically and include an export checksum to identify the matching report snapshot.
- [x] Verify `output/report.json` contains `started_at`, `finished_at`, `requests_total`, `requests_blocked`, `requests_by_status`, `jobs_by_source`, `duplicates_linked`, `jobs_new`, `jobs_removed`, `jobs_changed`, and `estimated_cost_usd`.
- [x] Source counts represent live database totals; lifecycle counts are strictly per-run. Include source outcomes and configured limits as partial-run context.
- [x] Finalize the compact submission README (498 words): setup, access/failed approaches, lifecycle/recovery, dedupe, controls and cost/1,000 with explicit rate/traffic assumptions.
- [ ] Record the Loom: demonstrate a real crawl and explain access, reconciliation, safe removals, dedupe, and efficiency decisions in under five minutes.
- [ ] Review tracked files for credentials; commit the latest real exports and intended code changes when ready to submit.
- [ ] Confirm private repository access for `gibbsdylan`, push before the deadline, and submit repository and Loom links through the assessment form.

**Acceptance:** the evaluator can reproduce the live crawl and offline tests without manual code changes, and the committed exports are substantiated by actual runs.

**Clean-source rehearsal (2026-10-09):** a separate temporary Git index/checkout
included current uncommitted runtime files/tests and excluded local credentials,
environments, captures and old exports. An uncached build plus fresh UUID-named
database produced six real jobs (two/board) using 18 requests. The incremental run
preserved all original first-seen/hash/canonical values, skipped fresh details and
added five pending listings, with zero changes/removals. Default/absolute-fixture
test forms each passed 88 tests and all fixture runs/replays, with proxy credentials
cleared. Export checks passed after both crawls and tests. All nine live-table
fingerprints, export hashes, staging and HEAD were unchanged; only the new isolated
project/volume was removed. Evidence: `reproducibility-findings.md`. The final
committed private GitHub clone/access check remains open.

**Final-default release rehearsal (2026-10-10):** current candidate snapshot tree
`0d69d133db8b8ea3fa1c32c535cddd2af315541c` built uncached into an empty UUID database.
Actual defaults produced 52 real listings across all boards; incremental run added 37,
preserved all original first-seen/hash/canonical values and made zero fresh-original
detail requests. LinkedIn 429 stopped safely. Both offline test forms passed 115 tests
plus all fixture runs/replays; exports verified after crawls/tests. All eleven live
table fingerprints, intended export hashes, staging and HEAD stayed unchanged; isolated
resources were cleaned up. Secret audit/exclusions passed for candidate files/staging/
history. Final original exports verify at 134 stored/133 live/131 canonical jobs.
The SSH remote is reachable but main is still the old checkpoint; gh is unavailable
and privacy/collaborator access unverified. Explicit commit/push, committed remote-clone,
owner Loom recording/link and actual submission are the remaining release actions.
`submission-checklist.md` supplies owner steps and a 4m40s walkthrough outline.

## Immediate next work session

1. Obtain explicit commit/push authorization, inspect status/diff/log and rerun secret checks, stage intended files/latest exports and release the verified candidate.
2. Owner confirms Private visibility and `gibbsdylan` access; verify the final committed remote clone after push.
3. Record/share the <=5-minute Loom and submit repository/Loom links before 2026-10-10T22:12Z.
4. Optional later improvements: further bounded sampled queue growth (265 pending) and confirmed-positive dedupe holdout. These do not justify a general 95%/recall claim from the current development samples.

Keep evidence of access experiments and unresolved decisions as implementation progresses. Finalize source-specific details from observed behaviour rather than assumptions.
