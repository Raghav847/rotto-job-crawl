# Current status and handoff

Last updated: 2026-10-10T00:25Z. Submission technical checks and final audit passed; owner release actions remain.

## Active task

Owner explicitly authorized commit/push of the verified release, with
`submission-checklist.md` and agent instructions excluded. Root `.gitignore` now
excludes `/submission-checklist.md`, `/AGENTS.md` and `/agents.md`; these local files
remain available for handoff but are not release contents. Release audit, intended
staging, commit/push and remote verification are in progress. Final privacy/collaborator
confirmation, Loom recording/share URL and assessment submission remain owner actions.

Submission preparation is complete on the technical side. README is condensed to
498 whitespace-delimited words; `submission-checklist.md` contains final owner actions
and a timed <=5-minute Loom outline. No recording, commit, push or assessment submission
has been made. GitHub CLI is absent; SSH remote reachability is confirmed but does not
prove privacy/collaborator access. Owner must verify private visibility and `gibbsdylan`.

Final current-default rehearsal command:
`uv run --locked --offline python /var/folders/d4/ndfskpvx28gfdb9h90ng9fv00000gn/T/opencode/rehearsal.py`.
Evidence: `output/diagnostics/reproducibility-8b3eaa4cfc20/summary.json` and logs;
snapshot tree `0d69d133db8b8ea3fa1c32c535cddd2af315541c`. Uncached build, credential-free
runtime snapshot and empty fresh UUID database produced 52 jobs (16 Indeed/17 LinkedIn/
19 Reed) using 109 requests. Incremental run added 37 (89 isolated total) using 88
requests, preserved every original first-seen/hash/canonical ID and re-fetched zero fresh
original details. LinkedIn 429 stopped safely; other boards completed bounded work.
Both default and absolute-fixture tests passed 115 tests plus all fixture runs/replays;
exports verified after crawls/tests. Isolated project/network/volume removed, no test
databases left. All eleven original persistence-table fingerprints, main export hashes,
staged diff and HEAD were unchanged. These isolated rows are not main live volume.

Final original export verifier passed for 134 rows (133 live/131 canonical jobs/two
duplicate links). Readonly secret audit passed across 77 candidate paths, staged blobs,
70 unique history blobs/four commits. Source credentials/local capture exclusions are
confirmed. An intentional dummy unsafe-redirect URL was re-expressed without a literal
credential-bearing URL; test behavior and the final default-runtime suite remain valid.
`git diff --check` passed. `git ls-remote --heads origin` confirms remote main still at
`b3cd36dfbd1bbf37186b17b454e53e5a87a1ff3d`; current verified changes need explicit
commit/push authorization, then final committed remote-clone verification.

Release steps now: authorize commit/push -> confirm private/collaborator access ->
verify committed clone -> record/share Loom -> submit both URLs by 2026-10-10T22:12Z.
Keep the next working block focused on those release actions rather than optional
additional queue growth. Full final rehearsal evidence: `reproducibility-findings.md`.

Coordinated scaling/quality/efficiency pass is complete. Full commands, evidence and
limits are in `acceleration-findings.md`. Defaults now use software/data queries,
two HTTP pages/one Indeed page, twenty details/source, two-second HTTP pacing and
queue-aware discovery. `CRAWL_DISCOVERY=auto|always|never` skips sufficient backlog
rediscovery without losing unfinished checkpoints or fabricating cached sightings.
Indeed hidden/unverified preview filtering and recent saved-proof cleanup are tested;
both original invalid IDs are no longer pending. Stored good jobs are not removed.

Combined command:
`CRAWL_SOURCES=linkedin,reed,indeed CRAWL_DISCOVERY=auto CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=25 CRAWL_MAX_REQUESTS=250 CRAWL_MAX_SECONDS=480 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Run `output/runs/20261009T201653Z-c0f36616/`: 75 detail tasks, 68 initially accepted,
53 initially new, two changed, one explicit source-confirmed expiry. All sources
skipped discovery. 114 requests/45,726,100 decoded bytes/172.724 seconds; zero
LinkedIn/Reed network blocks, eighteen Indeed resource/request blocks and three safely
rejected selections. Per-source/global throughput, traffic and distinct cost units
are now reported. USD rate remains unavailable and all cost estimates remain null.

Successful-run evidence triage/random sampling found two issues despite initial
68/68 description agreement: an Australia-relocation advert mis-tagged GB and a
copied careers-page related-jobs footer/missed “salary between” range. Regressions
now reject explicit mandatory overseas relocation while allowing overseas-market
mentions; parse between/and pay ranges and trim labelled multi-vacancy footers.
The bad new overseas row `indeed:331852b615036d5e` was explicitly archived in full
via identity/content-matched source proof (`listing_quarantine`), not marked source
expired or reset. One targeted real Birchwell refresh fixed 85000/100000/null period
and removed unrelated roles, preserving first seen. Latest run: one request/one change/
zero new or removals; exports include all 134 job rows (133 live plus one expired).

Ignored evidence: `accelerated-all-*`, `accelerated-sample-*` and
`accelerated-after-repair-*` under `output/reviews/`. After repair, 67 active successful
observations have matching main descriptions/zero triage flags. Fourteen valid original
sample records were inspected in full and one quarantined; new cohort is sampled/
triaged, not a full manual census. No general/random 95% accuracy claim is made.

Independent holdout (`dedupe_holdout_labels.json`/`dedupe_holdout_pairs.json`) freezes
thirteen source rows, seven unused inspected negatives (all rejected), and one
ambiguous/unscored JPMorgan cross-board pair. No confirmed holdout positives, so
precision/recall stay null. Report: `output/reviews/dedupe-holdout-report.json`.
`docker compose build crawler && make test` passed 115 tests plus fixture replays.
Export verification passes for all 134 rows/one current logged request. SQL confirms
phantom pending IDs absent, full invalid-row archive and 133 live/131 canonical jobs.
`git diff --check` passed. Pending work: 39 Indeed/148 LinkedIn/78 Reed; repeat bounded
batches with flag/sample review, extend confirmed positives, and finish release tasks.

Historical implementation steps for this pass: saved Indeed discovery captures prove
both failed IDs are aria-hidden preview nodes absent from decoded result metadata.
Discovery now rejects only that evidenced combination, preserving metadata-backed
hidden results, visible fallbacks and no-metadata fallbacks. Supporting queue cleanup
never deletes/removes stored jobs; later verified metadata clears the artefact cache.

Added `CRAWL_DISCOVERY=auto|always|never` (default auto). Auto drains a sufficient
actionable queue without repeatedly fetching search heads; unfinished discovery
cycles still resume. Explicit never leaves discovery checkpoints unchanged. Added
per-source request/byte/block metrics, accepted/new throughput and separate request-
attempt/listing-fetch cost units. Actual proxy rate remains optional/unknown, so USD
estimates stay null. Review tooling supports successful-run selection, discrepancy
triage and seeded per-source random samples; dedupe tooling ranks unlabelled real
cross-board candidates without fetching URLs.

`docker compose build crawler && make test` passed 110 tests plus fixture runs/replays.
Next: live artefact cleanup with two Indeed first pages/no details, then one bounded
multi-board queue batch that supplies benchmark, accuracy triage/sample and holdout
evidence together. Record exact runs before increasing budgets further.

Real dedupe evaluation and scoped source-reference matching are complete. Added a manual manifest and frozen corpus:
`tests/fixtures/real_dedupe_labels.json` and `real_dedupe_pairs.json` (26 source
snapshots, 16 pairs: two positives/fourteen negatives). Captured title/location/full
description agreement is required when freezing; only contract fields and verified
job-reference metadata are copied, not source scripts or credentials.
Command: `uv run --locked --offline python -m crawler.dedupe_review --freeze --report output/reviews/real-dedupe-baseline.json`.
Baseline: TP=1, FN=1, FP=0, TN=14; precision 1.0/recall 0.5 on this curated development
set, not a general estimate. Leidos matched; Tesco/Tesco Technology was the miss.

Implementation/tests complete: `Listing.matching_evidence` carries verified single-page
LinkedIn employer-reference metadata through the shared observation/reconciliation
service. `listing_match_evidence` binds issuer/reference to current content hashes;
matching evidence and canonical changes share the transaction. Feature caches track
evidence fingerprints and rule version 2. A legal-employer candidate index supports
the explicit Tesco recruitment-channel rule; no general brand aliases or arbitrary
suffix stripping. Matching requires the correct issuer/channel, same named legal
employer/requisition stem, exact title/concrete workplace/full-description corroboration.

Updated frozen corpus: TP=2/FN=0/FP=0/TN=14 on the 16 curated pairs. Command:
`uv run --locked --offline python -m crawler.dedupe_review --report output/reviews/real-dedupe-updated.json`.
`docker compose build crawler && make test` passed 102 tests and all supplied fixture
runs/replays, including nine new parser/corpus/transaction tests with near negatives,
metadata-only merge/count/hash preservation, metadata cache invalidation/splits,
wording edits with omitted evidence, delayed input and rollback.

Live verification command:
`CRAWL_SOURCES=linkedin CRAWL_QUERIES="Tesco Identity" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=10 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS=linkedin:4470379586,linkedin:4470374657 CRAWL_FORCE_REFRESH=0 make crawl`.
Run `output/runs/20261009T191325Z-f17e1383/`: three requests/no blocks/938,661
decoded bytes; two accepted refreshes, zero new/changed/removed listings. Both issuer/
reference pairs persisted and the Tesco copies linked with `scoped_recruitment_channel`.
Older canonical `4ad628b5-d616-53a5-b935-48e63f8c5a30` survives; original first-seen
timestamps/hashes and the Leidos grouping are unchanged. Rule-version backfill indexed
82 rows without fetching details. Export verifier passed for all 82 rows/three logged
requests; `git diff --check` passed. Current totals: 82 live listings, 80 canonical
jobs, two duplicate links. Source-field review remains complete for all 82.
Pending queues: 57 Indeed, 162 LinkedIn, 97 Reed. Full evidence/limitations/commands:
`dedupe-findings.md`. The curated set has only two positives/no holdout; extend it with
more independently selected cross-board positives and wording variants during scaling.

Indeed expansion and field review are complete. Command:
`CRAWL_SOURCES=indeed CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom,London,Manchester" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=22 CRAWL_MAX_REQUESTS=180 CRAWL_MAX_SECONDS=600 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Run `output/runs/20261009T031307Z-8aadcfaa/` discovered 82 IDs across six public
first pages, skipped five fresh details and accepted 20 new listings. Two invalid
identity selections were safely rejected. 78 requests/33,837,715 decoded bytes,
two blocked request records, zero content changes/removals. Export verifier passed
for all 82 rows (28 Indeed, 26 LinkedIn, 28 Reed; 81 canonical jobs). 57 Indeed
pending IDs remain. All twenty new rows have now had independent field/full-description
review with no new extraction defect. All twenty description word streams and all
twenty ID-bound discovery dates agree, with zero conflicting source-date sets.
Documented coverage is 82 total: 28 Indeed, 26 LinkedIn and 28 Reed. All three boards
meet the 25-reviewed milestone; this is a development census, not random grading.

Reviewed cases include 38 Degrees' UK-eligible home/remote role and full-time four-day
week, one-sided salary ceilings, permanent-only hours categories, square logos versus
banners, absent logo URLs and Huxley's headline/prose salary discrepancy. No company,
hours, salary period, or pay proration was guessed. Search salary snippets may carry
USD/EUR currency flags without amounts; these are not pay or workplace evidence.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T031307Z-8aadcfaa --ids indeed:1f09c85980aadf7c indeed:24d1d7e6e352b94b indeed:45a469bc422defd3 indeed:4f29f72d41501e80 indeed:54e89af28ef83fe4 indeed:6ab35cf4f2dd1816 indeed:754a8d49290f6cec indeed:757a85d63473258a indeed:89fc15da595f38e2 indeed:d8aa52d3c7900fba indeed:f329a774c8defe83 indeed:13abf4d64f8f2cdc indeed:16e55cbef0d97445 indeed:171dee089cc0a51c indeed:1cb9991f8f8dfafd indeed:2c8b21e91b74d8ba indeed:345023d7eb6fa3ee indeed:3e49154a291c8bac indeed:5180a8b50baf518b indeed:95bd9c478263f20d`.
The read-only helper now compares discovery dates explicitly and exposes source-card
job-type/pay metadata for corroboration. Full descriptions and metadata were inspected.
Per-row notes: ignored `output/reviews/indeed-expansion-decisions.json`; durable findings:
`accuracy-findings.md`. Export verifier passed for all 82 rows/hashes/counts and 78
requests; `git diff --check` passed. No parser/data correction was needed in this batch.

Unresolved efficiency item: selected IDs `0f1e2d3c4b5a6978` and `890abcdef0123456`
produced no board-owned identity, so no rows were inserted or removed. Inspect source
discovery artefacts and suppress invalid retries with explicit evidence; do not use
search absence or failure as removal evidence. Their failed queue entries remain.

Reed expansion and field review are complete. Command:
`CRAWL_SOURCES=reed CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=15 CRAWL_MAX_REQUESTS=40 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Run `output/runs/20261009T022757Z-4f3a1143/` discovered 100 distinct IDs across
four pages, skipped 12 fresh details and accepted all 15 details. 19 requests, no
blocks/failures/rejections; 5,866,364 decoded bytes; zero changes/removals. Export
verifier passed for 62 rows (8 Indeed, 26 LinkedIn, 28 Reed; 61 canonical jobs).
97 Reed pending IDs remain alongside 105 LinkedIn IDs. All 15 new rows have now had
full source-field review, with no new extraction defect. Documented coverage is 62
total: 8 Indeed, 26 LinkedIn, 28 Reed. Reed and LinkedIn meet the 25-reviewed milestone;
this is development review, not random grading or a general accuracy estimate.

Three Norton Rose descriptions have abrupt endings, identically present in both
visible text and JSON-LD; all board-served text is retained. FDM's displayed permanent/
full-time employment metadata is separate from client assignment duration. Oliver
James's headline/JSON-LD 650–750/day remains authoritative over 700–750/day prose.
Daily/annual pay, null compensation/logos, title differences and UK workplaces were
checked. Real Norton Rose/Connells negative dedupe examples were recorded.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T022757Z-4f3a1143 --ids reed:57147108 reed:57168860 reed:57265783 reed:57282800 reed:57306764 reed:57312223 reed:57327650 reed:57332819 reed:57334111 reed:57354540 reed:57364154 reed:57364627 reed:57364884 reed:57364885 reed:57379454`.
All 15 full description word streams match; metadata/full text were also independently
inspected. The read-only helper now writes `output/reviews/source-metadata.txt` and
records structured-description lengths/endings. The three-source-description check
was followed by regenerating the full fifteen-record inventory.
Per-row notes: ignored `output/reviews/reed-expansion-decisions.json`; durable findings:
`accuracy-findings.md`. Export verification passed for all 62 rows/19 requests;
`git diff --check` passed. No parser/data correction was needed in this batch.

LinkedIn expansion and field review are complete. Command:
`CRAWL_SOURCES=linkedin CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=12 CRAWL_MAX_REQUESTS=40 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 make crawl`.
Run `output/runs/20261009T021040Z-a7889f70/` discovered 70 IDs, skipped 12 fresh
details, accepted 10 new listings and rejected two with unconfirmed UK eligibility.
14 requests, no blocks, 4,062,109 decoded bytes; zero changes/removals. Export
verifier passed for all 47 rows (8 Indeed, 26 LinkedIn, 13 Reed; 46 canonical jobs).
That run left 45 LinkedIn pending IDs alongside 72 Reed IDs. All ten new rows have
now had full source-field review, including one salary correction described below.
Documented coverage is 47 total: 8 Indeed, 26 LinkedIn and 13 Reed. LinkedIn meets
the 25-reviewed milestone; this is development review rather than random grading.

Full metadata/descriptions have now been inspected for all ten new rows. One confirmed
Wise salary defect: `linkedin:4437559548` contains both `£111,000 - £145,000k` and
the unambiguous `111K - 145K GBP`. The old parser ignored the GBP-text statement and
stored an upper bound of 145 million. Explicit GBP prefix/suffix support and narrow
corroboration for redundant thousands notation now parse 111000/145000, with null
period because neither statement supplies one. Unresolved conflicts remain null and
no arbitrary salary cap is used. Captured-page CLI verification passed.

Added optional `CRAWL_REFRESH_IDS` maintenance targeting (existing source:id values
only, from configured sources, first within detail budgets) to refresh this one fresh
row without re-fetching the other 25 LinkedIn rows. Unknown IDs cannot dispatch a
listing request. `docker compose build crawler && make test` passed 93 tests plus
all fixture runs/replays, covering GBP/corroboration/conflict cases and targeted
maintenance, including correct freshness-skip accounting for explicit targets.

Correction command:
`CRAWL_SOURCES=linkedin CRAWL_QUERIES="Wise Account Sharing" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=1 CRAWL_REFRESH_IDS=linkedin:4437559548 CRAWL_FORCE_REFRESH=0 CRAWL_MAX_REQUESTS=10 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 make crawl`.
Run `output/runs/20261009T021854Z-86fa5234/` accepted one targeted refresh using
two requests/no blocks/625,476 decoded bytes. One content change, zero new/removals;
SQL confirms 111000/145000/null period and original first-seen/canonical values.
The broad search queued further candidates; current queue is 105 LinkedIn/72 Reed.
Export verifier passed after both runs. The final rebuilt runtime passes 93 tests
and all fixture runs/replays; all ten source description word streams match.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T021040Z-a7889f70 --ids linkedin:3955668958 linkedin:4030407849 linkedin:4285959027 linkedin:4393533375 linkedin:4401592205 linkedin:4412048387 linkedin:4414737700 linkedin:4425784558 linkedin:4434022510 linkedin:4437559548`.
Per-row decisions: ignored `output/reviews/linkedin-expansion-decisions.json`;
durable conclusions and exact evidence: `accuracy-findings.md`.
`git diff --check` passed after final code/documentation edits.

The remaining five stored listings are reviewed: `indeed:9f0d5e9babff5535`,
`linkedin:4470379586`, `reed:57421313`, `reed:56212211`, `reed:57115738`.
No new source-field extraction defect was found; all five complete description word
streams agree, and full text/metadata were inspected. Per-row conclusions are in
`accuracy-findings.md` and ignored `output/reviews/five-listing-decisions.json`.
Documented review coverage is now all 37 live rows: 8 Indeed, 16 LinkedIn, 13 Reed.
This is a development census, not random grading or a general accuracy estimate.

FDM's returners role explicitly offers two years of full-time consultant employment;
training language alone is not grounds to exclude it. DFYNE's unbounded upper salary
and September 9 ID-matched date agree with source evidence; later omitted dates/null
logos were checked against historical card and branding payloads. Source advertiser
names/titles are retained for recruiter and automation-role listings.

New real dedupe candidate: `linkedin:4470379586` (Tesco) and `linkedin:4470374657`
(Tesco Technology), same title/place/description and named legal employer Tesco Stores
Limited. Source identifiers `209433TescoUK`/`209433Technology` share a numeric stem;
timestamps differ by one second. Canonical IDs remain separate pending a scoped
matching-policy review. The evidence helper now exposes structured source identifiers.
Do not infer a general brand alias or strip arbitrary suffixes from requisitions.

Verification commands:
`uv run --locked --offline python -m crawler.accuracy_review --ids indeed:9f0d5e9babff5535 linkedin:4470379586 reed:57421313 reed:56212211 reed:57115738` (five matching descriptions),
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T011254Z-5b554641 --ids indeed:9f0d5e9babff5535` (historical exact posting-date evidence),
`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`
(37 rows/four logged requests from the last live run), and `git diff --check` passed.
No new live request or data correction was needed. SQL confirmed zero due 24-hour
refreshes on every board at this milestone.

Clean-source reproducibility rehearsal is complete. A temporary Git index/checkout
contained current runtime code/tests (including uncommitted changes), with no local
credentials, host environment, captures or pre-existing exports. Built without layer
cache, started a new Compose project/volume and fresh UUID-named database, then ran
live/incremental crawls and both offline test forms. Exact commands and scope are in
`reproducibility-findings.md`.

Evidence: `output/diagnostics/reproducibility-a1735ecd7509/summary.json` and companion
logs/reports. Snapshot tree `f400cfe9dc343e407c90834c8ce81e8dc8ad022b`; base image
was already available on the host. Driver command:
`uv run --locked --offline python /var/folders/d4/ndfskpvx28gfdb9h90ng9fv00000gn/T/opencode/rehearsal.py`.
First isolated run produced six listings (two/board), 18 requests, no blocks.
Incremental run retained all six original first-seen/hash/canonical values, skipped
fresh details (2 LinkedIn, 2 Reed, 1 Indeed), and added five rows; a training advert
was excluded. 11 isolated rows, 18 requests, zero content changes/removals.
Export verifier passed after each live run and after tests. Both `make test` and
absolute-path `FIXTURE_PATH=... make test` passed 88 tests plus fixture replays with
proxy credentials cleared. No temporary unit/fixture databases remained.

Ordered fingerprints of all nine original live persistence tables, export-file
hashes, Git HEAD and staged diff were unchanged. Isolated project/volume/network
was cleaned up; the main database/export still has 37 live rows/36 canonical jobs
and 72 pending Reed IDs. The eleven rehearsal rows are not included in live totals.
Final committed GitHub-clone verification remains part of submission preparation.
`git diff --check` passed after the reproducibility documentation update.

Durable queue/checkpoint implementation and bounded live recovery validation are complete.
Added `pending_candidates`, `crawl_progress`, and `discovery_checkpoints` supporting
tables plus `crawler/progress.py`. Successful discovery commits sightings, ID-bound
date hints/pending IDs, and the next traversal position together. Successful details,
confirmed removals and exclusions acknowledge queue rows transactionally. Failed or
interrupted details remain pending; queue replay alone never advances job sightings.
An unfinished matching plan resumes within the refresh interval; completed/changed/
stale plans restart discovery while retaining pending candidates. Reports retain
partial source progress and show cycle/queue counts even on handled interruptions.

`docker compose build crawler && make test` passed 88 tests plus all fixture runs/
replays. Eleven new recovery/checkpoint tests cover budget/page resume, actual Python
interrupts, completed-detail acknowledgement, changed scopes, stale plans, date hints,
transaction rollback and retry rotation. HTTP requests now have durable start events;
an interrupted request is finalized/accounted in `requests.jsonl` (one added test).
Live interruption verified: `CRAWL_SOURCES=reed CRAWL_QUERIES="data engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=3 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=20 CRAWL_MAX_SECONDS=180 CRAWL_REQUEST_DELAY=10 CRAWL_SAVE_PAGES=1 make crawl`,
with SIGINT sent to the crawler's Python process after eight seconds using
`docker exec "$container_id" pkill -INT -f '^/app/.venv/bin/python[^ ]* -m crawler.run$'`.
Run `output/runs/20261009T014538Z-1ddef7be/` exited 130 as expected, exported all
35 unchanged rows, and retained 25 queued IDs plus page-two checkpoint. One logged
request, no blocks or lifecycle transitions. Export verifier passed. Database confirms
cycle `fc7cc33a-ce6f-4722-bf0c-b288c7a4ad0f` was unfinished and its saved URL has no
session parameter.

Resume command: `CRAWL_SOURCES=reed CRAWL_QUERIES="data engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=3 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=20 CRAWL_MAX_SECONDS=180 CRAWL_REQUEST_DELAY=1 CRAWL_SAVE_PAGES=1 make crawl`.
Run `output/runs/20261009T014612Z-1e09c794/` resumed the same cycle, starting at
page two. Two discovery requests plus two details accepted `reed:56212211` (London)
and `reed:57115738` (Milton Keynes); zero blocks/changes/removals. 74 distinct IDs
across the capped three-page cycle, 72 pending candidates remain. 4 requests,
1,446,817 decoded bytes. Cycle is now completed; next normal invocation rechecks
search heads while retaining the queue. Export verifier passed for all 37 rows and
four logged requests. Full policy/evidence: `recovery-findings.md`.

Final reporting check: discovery ending without a next link still reports `limited`
when details remain queued. Rebuilt runtime and reran `make test` plus export
verification after that correction: 88 tests/fixture replays and all 37 export rows
passed. `git diff --check` passed. No crawl process remains active.

Reviewed the 12 new listings from the broader discovery run. Four Indeed posting
dates were missing despite identity-matched search-card evidence; all are now corrected
through live successful detail observations/shared reconciliation. Other reviewed
fields agree, and all 12 complete description word streams match. Findings and
per-listing decisions are in `accuracy-findings.md`. Documented reviewed totals are
32 distinct listings: 7 Indeed, 15 LinkedIn, 10 Reed (three stored rows are outside
these review batches). This is development evidence, not general accuracy grading.

Verification: `docker compose build crawler && make test` passed 76 tests and all
three lifecycle fixture runs/replays. An integration test proves that failed date
enrichment preserves good rows, successful enrichment preserves first seen/canonical
ID, and the content hash changes. The priority test includes an unknown result before
the known missing-date row and confirms that enrichment gets the one-detail budget.

First maintenance command: `CRAWL_SOURCES=indeed CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom,London" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=8 CRAWL_MAX_REQUESTS=120 CRAWL_MAX_SECONDS=300 CRAWL_FORCE_REFRESH=1 CRAWL_SAVE_PAGES=1 make crawl`.
Run `output/runs/20261009T012626Z-3191f6e3/`: all eight details accepted;
two posting dates corrected (London Redhorse and Hippo). 41 logged requests,
zero new/removed rows, export verifier passed. Manchester Redhorse and VACAC were
not rediscovered in current scopes, so their dates remain null. Added priority for
known missing-date enrichment after due refreshes and before new IDs.

Second correction command: `CRAWL_SOURCES=indeed CRAWL_QUERIES="VACAC,Redhorse International" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=80 CRAWL_MAX_SECONDS=300 CRAWL_SAVE_PAGES=1 make crawl`.
Run `output/runs/20261009T012810Z-11d49761/`: two details accepted, two date
corrections, zero new/removed rows; 25 requests/4,947,294 decoded bytes. Both remaining
dates are now stored; first-seen timestamps/canonical IDs match pre-review records.
`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`
passed after each correction run (35 rows; 41/25 logged requests respectively).

Independent evidence command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T011254Z-5b554641 --ids linkedin:4470374657 linkedin:4449078328 linkedin:4449465893 linkedin:4296369615 reed:57321518 reed:57424368 reed:57411163 reed:57435600 indeed:1c2b4cc4f74044cd indeed:ef4b93145626d5c7 indeed:0ee5965a1444f71a indeed:a471df05393f6006`.
Produces ignored `output/reviews/source-evidence.json` and per-listing full-description
text. It does not fetch pages. A four-ID Indeed-only invocation was used to inspect
branding payloads, then the full twelve-record inventory was regenerated successfully.
`git diff --check` passed after the final code/documentation edits.

Immediate next steps:
1. Obtain explicit commit/push authorization, recheck secret audit/status/diff/log and
   stage only intended code/docs/fixtures/latest exports. Final remote main is still old.
2. Owner confirms repository Private and `gibbsdylan` collaborator access; gh is unavailable.
3. Verify the final committed remote clone, record/share the <=5-minute Loom using the
   outline, and submit repository/Loom URLs before 2026-10-10T22:12Z.
4. Optional further work: bounded queue growth (265 remaining) with sampling/triage and
   independently confirmed positive dedupe holdout. Do not claim general recall/95% accuracy.

Discovery implementation is validated: source next links, LinkedIn guest offsets,
query/location partitions, repeated-page/URL-loop guards, overlapping-ID suppression,
and per-query progress. Indeed stops later scopes at page one after observing a
sign-in pagination gate, while retaining access to other public first pages/details.
Verification: `docker compose build crawler && make test` passed 74 tests and all
three supplied fixture runs/replays. Added integration checks for guest offsets and
continued public scopes after a sign-in gate. Repeated after the Reed location fix;
the same suite passed.

Broader run verified: `CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom,London" CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=5 CRAWL_MAX_REQUESTS=150 CRAWL_MAX_SECONDS=600 CRAWL_SAVE_PAGES=1 make crawl`.
Evidence: `output/runs/20261009T011254Z-5b554641/`. Discovered 197 LinkedIn,
102 Reed, 56 Indeed IDs; added four valid listings per board, no content changes/removals.
64 logged requests, 19,870,765 decoded bytes; one Indeed identity extraction failure
was safely rejected. Export verifier passed (35 rows). Reed ignored `location=London`:
captured heading/form and next link remained UK-wide. Corrected location URL generation
to the page's declared `-jobs-in-london` path.

Follow-up: `CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom,London" CRAWL_MAX_PAGES=3 CRAWL_MAX_DETAILS=0 CRAWL_MAX_REQUESTS=100 CRAWL_MAX_SECONDS=600 CRAWL_SAVE_PAGES=1 make crawl`.
Evidence: `output/runs/20261009T011524Z-6be07a73/`. Discovered 208 LinkedIn,
266 Reed, 52 Indeed IDs. Reed London heading/input/next-link scope is now verified.
LinkedIn produced 80 unique IDs per completed three-page scope (offsets 60 and 70),
then returned 429 on the final scope's second page; stopped that source safely.
Indeed attempted one page-two sign-in gate then traversed all remaining first pages.
Zero details and lifecycle transitions; all 35 rows/34 canonical jobs retained.
51 logged requests, 13,223,928 decoded bytes, seven blocked request records (including
browser subresources). `docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`
passed after both live runs. `git diff --check` passed.

### Latest discovery experiment

Command: `CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=0 CRAWL_MAX_REQUESTS=100 CRAWL_SAVE_PAGES=1 make crawl`.
Run evidence: `output/runs/20261009T003903Z-bd03e2fe/`.

- Reed followed its supplied next-page link and found 51 distinct IDs across two pages.
- LinkedIn full-page `start=25` returned the same 60-ID set; repeated-page detection stopped it.
- Indeed's constructed second page reached a public sign-in landing page. The stale
  rendered ID set made it look repeated; it is now classified as an auth gate.
- 24 logged requests, no scheduled details, zero lifecycle transitions; 23 stored rows retained.
- `crawler.discovery_evidence` is a new offline inspection helper. It confirms LinkedIn's
  first captured page has 60 actual result cards, not merely recommendation links.

Follow-up command: `CRAWL_SOURCES=linkedin,indeed CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=0 CRAWL_MAX_REQUESTS=100 CRAWL_SAVE_PAGES=1 make crawl`.
LinkedIn's public `/jobs-guest/jobs/api/seeMoreJobPostings/search` at offset 60 yielded
10 new IDs (70 total). Indeed's real next link still reached a sign-in gate; do not
use accounts or attempt that gate. Expand Indeed through public first-page query/location
partitions. Preserve the last successful public search URL for detail selection.

## Verified foundation

- All three boards have produced real UK jobs.
- Latest known database: 49 Indeed, 37 LinkedIn, 47 Reed live rows; 133 live listings,
  131 canonical jobs, two linked duplicates. 134 job rows exported including one expired;
  one invalid overseas import fully preserved separately in quarantine.
- Current durable pending queue: 39 Indeed, 148 LinkedIn and 78 Reed candidate IDs.
- Latest known suite: 115 tests plus supplied lifecycle fixture and replay checks pass.
- Docker runtime packages Python 3.12, pinned dependencies and Chromium; host needs
  Docker Compose/Make. PostgreSQL runs on local port 55432 with a persistent volume.
- Every live run exports all stored rows and a report; the export verifier checks
  table equality, hashes, source/canonical counts and request-log accounting.
- Current workspace contains uncommitted accuracy and efficiency changes. Inspect
  Git status; do not revert or commit them automatically.

## Recent verified work

- Accuracy review corrected five LinkedIn salary records and adjacent-inline-word
  formatting; selected Indeed view payloads now work when the job is absent from search cards.
- Dedupe links Leidos' Bristol Software Engineer across Indeed/LinkedIn while retaining
  its original canonical ID; other workplaces/roles remain conservatively separate.
- Indeed lean policy: the same three-detail workload fell from 224 requests/12.74 MB
  decoded bodies to 24 requests/6.31 MB, with all three refreshed and no content changes.
- All-board follow-up accepted one new job/source using 23 requests total and about
  5.27 MB decoded bodies. This is limited development coverage, not a large accuracy sample.

## Commands

```sh
docker compose up -d
make crawl
make test
FIXTURE_PATH=/absolute/or/relative/fixture.json make test
docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports
```

Bounded development example:
```sh
CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=3 CRAWL_SAVE_PAGES=1 make crawl
```

`CRAWL_FORCE_REFRESH=1` bypasses freshness for explicit maintenance. Do not leave it
enabled for routine runs. Tests use the already-built image; rebuild after code/test edits.

## Open work

- Queue-aware defaults and 25-detail/source pacing are verified at bounded scale;
  larger sustained loads/order/rate behavior still need measurement. No untested
  concurrency or general blocking/throughput claim is justified.
- The all-board 25-reviewed milestone passed; later growth is triaged/randomly sampled,
  not wholly manually reviewed. Continue broader layouts and flagged/full random review;
  simple metadata agreement cannot establish eligibility or general accuracy.
- Durable pending candidates/source-scope checkpoints and bounded live SIGINT recovery
  are verified. Larger workload recovery/performance and source-specific long-run
  rate/ordering behavior still need measurement.
- Proxy USD/GB rate is unknown; cost fields remain null. Decoded bytes are not billed bytes.
- Current-code clean-source/fresh-database rehearsal passed. Final committed GitHub
  clone/access check, final exports/README, <=5-minute Loom and submission are pending.
  Confirm repo privacy/access for `gibbsdylan` before submission.
- GitHub CLI was unavailable in an earlier session; repository privacy has not been
  independently confirmed by the agent.

## Do not infer

Do not claim 95%+ general accuracy from current samples. Do not infer removal from
search completeness, absence, blocked pages or capped queries. Do not treat a browser
resource blocked locally as a network request. Do not download logo images.
