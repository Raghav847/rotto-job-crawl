# Coordinated scaling, quality and efficiency pass — 2026-10-09

## Faster operating workflow

- `CRAWL_DISCOVERY=auto` is the default: drain an actionable backlog large enough for
  the detail budget before fetching more search heads. An unfinished discovery cycle
  still resumes. `always` rechecks heads; `never` processes queued/due/targeted details
  without altering saved discovery checkpoints. Cached queue entries are not sightings.
- Default clean-machine coverage is software/data-engineer queries, two LinkedIn/Reed
  pages, one Indeed page, twenty details/source, two-second HTTP pacing, 300 requests
  and ten minutes. `INDEED_MAX_PAGES=1` avoids the known logged-out page-two gate;
  an explicit diagnostic override is available. Existing environment overrides remain.
- One run produces source captures, per-source throughput/block/traffic metrics,
  atomic exports, independent evidence triage and seeded random-review inputs.
- `crawler.accuracy_review --observed-in-run --sample-per-source 5 --seed 20261009`
  selects a reproducible sample of successful observations; `--label` keeps all-row
  and sample artefacts side by side. Discrepancy flags are review aids, not an automatic
  validity or accuracy grade. Read full descriptions in the sample and inspect flags.
- Crawl fetching remains sequential. Twenty-five HTTP details/source at two-second
  pacing succeeded without a LinkedIn/Reed block in this pass; this is evidence for
  measured pacing, not an untested concurrency claim.

## Indeed non-listing artefacts

Saved source captures show `0f1e2d3c4b5a6978` and `890abcdef0123456` under
`aria-hidden=true` and absent from the decoded job-result metadata. The parser now
rejects only that evidenced combination. Metadata-backed hidden results, visible
fallbacks and no-metadata fallbacks are preserved. No IDs are hard-coded in the rule.

Supporting cleanup suppresses unknown pending artefacts and caches the reason for
the refresh interval; it never deletes/removes stored jobs. Later verified result
metadata clears that artefact cache. Recent saved discovery proof can clean older
pending previews without making new observations or requests.

Live head-check command:
`CRAWL_SOURCES=indeed CRAWL_QUERIES="software engineer" CRAWL_LOCATIONS="United Kingdom,London" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=0 CRAWL_DISCOVERY=always CRAWL_MAX_REQUESTS=80 CRAWL_MAX_SECONDS=180 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Evidence: `output/runs/20261009T200923Z-c1a1e3ac/`. Both pages exposed one filtered
preview and fifteen real results. One then-current pending entry was suppressed;
recent saved proof cleaned remaining pre-fix entries in the subsequent batch. SQL
confirms neither original failed ID remains pending. Stored job lifecycle was untouched.

## Combined live benchmark

```sh
CRAWL_SOURCES=linkedin,reed,indeed CRAWL_DISCOVERY=auto CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=25 CRAWL_MAX_REQUESTS=250 CRAWL_MAX_SECONDS=480 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl
```

Evidence: `output/runs/20261009T201653Z-c0f36616/`.

| Source | Detail tasks | Accepted observations | Initially new | Requests | Decoded bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| LinkedIn | 25 | 21 | 12 | 25 | 8,576,191 |
| Reed | 25 | 25 | 19 | 25 | 6,822,693 |
| Indeed | 25 | 22 | 22 | 64 | 30,327,216 |
| Total | 75 | 68 | 53 | 114 | 45,726,100 |

All sources skipped rediscovery. Runtime was **172.724 seconds** (2m53s), about 23.6
accepted observations/minute. LinkedIn/Reed had zero network block records; Indeed
had eighteen blocked resource/request records and three identity/metadata extraction
failures, while twenty-two full details succeeded. Failures remain pending; no partial
data overwrote good rows. Two UK-ambiguous LinkedIn roles were excluded. A previously
stored Client Server listing explicitly stopped accepting applications and was safely
marked removed; no search absence was used.

These are measured outcomes on different pending work, not a workload-matched speedup
percentage. Accepted observations include refreshes and are distinct from new volume.
The new reporting separates those quantities and attributes traffic/requests by source.

## Sampling found defects that metadata agreement missed

All sixty-eight successful observations initially had matching visible descriptions
and no simple metadata discrepancy. A seeded five/source full-text review nevertheless
found two issues, demonstrating why reference agreement is not a validity grade:

1. `indeed:331852b615036d5e` is an Australian workplace advertised to UK candidates.
   Its title says Melbourne/Australia and applicants explicitly must move to Australia;
   the source's UK location/country flags are misleading recruitment metadata. A narrow
   mandatory-relocation/title contradiction check now rejects this even with GB metadata,
   while overseas-market mentions without mandatory relocation stay eligible.
2. `linkedin:4457381152` copied an employer careers page containing unrelated roles.
   Its own range is £85,000–£100,000, repeated as “salary between £85,000 and £100,000”.
   Supporting that explicit range grammar resolves the old conflicting single-amount
   parse. An explicitly headed, multi-vacancy footer is now excluded, while this role's
   application guidance is retained. No pay period is inferred.

The mistakenly inserted overseas row was repaired through `crawler.quarantine` with
identity/full-description-matched saved source evidence. The complete original row,
hash, lifecycle timestamps and evidence path are retained in `listing_quarantine`.
This targeted invalid-import repair is not a source expiry/removal transition or a
database reset. Ordinary failed/ineligible crawls still preserve stored good rows.

Repair command:
`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.quarantine indeed:331852b615036d5e output/runs/20261009T201653Z-c0f36616/indeed-browser/0218-detail.html`.
Then one real targeted detail refresh rewrote the corrected salary/description and
latest exports:
`CRAWL_SOURCES=linkedin CRAWL_DISCOVERY=never CRAWL_MAX_DETAILS=1 CRAWL_REFRESH_IDS=linkedin:4457381152 CRAWL_FORCE_REFRESH=0 CRAWL_MAX_REQUESTS=5 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 make crawl`.
One successful request, one content change, zero new/removals. SQL confirms
85000/100000/null period and removal of the unrelated footer.

After repair, evidence triage covers sixty-seven active successful observations with
zero flags and 67/67 main-description word agreement. Fourteen valid records from the
original fifteen-record sample have full-text/source-field inspection; one original
sample record is quarantined. This is a small development sample, not proof of 95%
general accuracy. Source diversity includes employment types, logos, salary ceilings,
overseas legal names, UK office requirements, and real content edits.

Review commands:
```sh
uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T201653Z-c0f36616 --observed-in-run --quiet --label accelerated-all
uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T201653Z-c0f36616 --observed-in-run --sample-per-source 5 --seed 20261009 --quiet --label accelerated-sample
uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T201653Z-c0f36616 --observed-in-run --quiet --label accelerated-after-repair
```
Ignored all-row/sample/after-repair evidence and triage files remain under `output/reviews/`.

## Independent dedupe holdout

`dedupe_holdout_labels.json` / `dedupe_holdout_pairs.json` freeze thirteen listings
and eight unused pairs after the matcher change. Seven independently inspected negatives
cover same-employer/office/staff-level but different technical scope, lead/senior roles
with distinct employer requisitions, and nearby London engineering roles at different
named employers. All seven are rejected. One plausible JPMorgan cross-board pair has
insufficient common-requisition evidence and remains explicitly unresolved/unscored.

Command:
`uv run --locked --offline python -m crawler.dedupe_review --freeze --labels tests/fixtures/dedupe_holdout_labels.json --fixture tests/fixtures/dedupe_holdout_pairs.json --report output/reviews/dedupe-holdout-report.json`.
This holdout has no confirmed positives, so precision/recall are null rather than
invented. The original curated two-positive/fourteen-negative corpus still passes.
More independently confirmed cross-board positives/wording variants remain necessary.

## Cost reporting and traffic allowance

The supplied assessment gives a 10 GB allowance but no USD/GB rate. No actual rate
is available in configuration. `estimated_cost_usd` and both cost/1,000 fields stay
null; `cost_rate_supplied=false` makes that explicit.

If the actual rate R is supplied as `PROXY_COST_PER_GB_USD`, estimated cost is
`decoded_bytes / 1,000,000,000 * R`. Request-attempt cost/1,000 and logical listing-fetch
cost/1,000 are reported separately; warmup, redirects/retries and browser resources are
included in traffic cost even when excluded from the logical fetch denominator.
Decoded bodies are not billed bytes: compression, protocol overhead and incomplete
response bodies are not measured. Provider-billed remaining allowance must be checked
through the user's supplied proxy usage information; do not infer it by subtracting
decoded bytes from 10 GB. No extra allowance request is justified from this pass alone.

## Final state and checks

`docker compose build crawler && make test` passed **115 tests**, all fixture runs and
idempotent replays. Export verification passed after repairs for **134 stored rows**
(one source-expired row included), **133 live listings** (49 Indeed, 37 LinkedIn,
47 Reed), **131 live canonical jobs** and two linked duplicates. The invalid overseas
snapshot is preserved separately. Pending work remains: 39 Indeed, 148 LinkedIn, 78 Reed.

The accelerated workflow is implemented and demonstrated; the queue is not fully
drained and the new cohort is triaged/sampled rather than wholly manually reviewed.
Repeat bounded batches with flag/sample review, expand confirmed dedupe positives,
then finish final clone/docs/cost assumptions/Loom/repository access/submission.
