# Durable decisions and discoveries

## Access

- LinkedIn/Reed work with lightweight Chrome-impersonated HTTP through the provided proxy.
- Indeed HTTP alone, legacy headless mode and browser-to-HTTP cookie handoff were blocked.
- Working Indeed path: full Chromium, normal native Chrome product token, automation
  compatibility flags, UK locale/timezone, homepage warmup and public selected-job panes.
- Oxylabs supports sticky-session username parameters. Derive the ephemeral suffix from
  provided env credentials; keep the same endpoint/account. Never record credentials/cookies.
- Direct Indeed `viewjob` navigation encountered anonymous auth gates. Public search `vjk`
  selects complete job panes without an account; bind pane ID and selected payload `jobKey`.
- Preserve security scripts/frames/endpoints. Lean mode skips repeated frontend CDN,
  consent UI and telemetry. Security-check overhead still varies by proxy/source behaviour.

## Extraction

- LinkedIn JSON-LD `identifier` can be the employer's requisition ID, not the board ID.
  Use the verified listing URL for source identity.
- Indeed sponsored click URLs can be opaque; `data-jk` provides the board ID.
- Indeed selected jobs can be absent from result cards. The explicit selected-view
  payload provides `jobKey`, `jobCountry`, header data and full description; page `country`
  alone is not workplace evidence. Reject logged-in payloads.
- Full descriptions come from the dedicated description region. Separate adjacent
  inline words and remove controls/styles, not employer-provided job requirements.
- Prefer dedicated compensation over conflicting prose. Explicit salary/pay-range
  statements in descriptions fill missing values; shares/assets/bonuses are not salary.
- `/yr`, `/hr`, repeated units and k-ranges are supported. Never assume a missing period
  or borrow it from another board's copy. Annual leave is not an annual salary statement.
- Company logos differ from wide banners. Read declared logo URL/branding JSON, never
  download the image. Preserve visible titles even if descriptions use alternate wording.
- “Permanent” alone does not specify working hours; do not guess full-time.
- Indeed's search-card `pubDate` can be available while the selected view omits dates.
  Carry exact ID-matched dates as candidate hints into successful detail observations.
  Existing known dates remain stable and explicit current detail dates take precedence.
  Known missing-date enrichment gets priority after due refreshes, before new IDs.
  Never rewrite source content from discovery-only or failed detail observations.
- Independent description review strips standalone presentation headings, not an
  employer's opening “Description -” prose. Four new Indeed null logos were verified
  against both absent containers and null declared branding-logo URLs.
- Reed can state PAYE and umbrella hourly rates for the same vacancy. Preserve the
  board headline/structured compensation; do not turn different pay bases into a range.
- An employment advert may include upskilling/returner-programme language. FDM's
  reviewed Reed listing explicitly commits to full-time consultant employment and
  client assignments; it is not a tuition-only training advert. Preserve source
  employment evidence rather than rejecting any description mentioning training.
- Preserve visible board titles despite more-specific employer prose (e.g. Reed's
  Senior Software Engineer describes production-support/automation engineering).
- Explicit GBP prefix/suffix salary statements are supported. Redundant thousands
  notation such as `£145,000k` can use the variant without redundant `k` only when
  another explicit clean statement corroborates that exact range. Wise's reviewed
  page also states `111K - 145K GBP`, supporting 111000/145000 with no stated period.
  No arbitrary salary cap is imposed; unresolved conflicting statements stay null.
- `CRAWL_REFRESH_IDS` is optional targeted maintenance: existing IDs from configured
  sources are scheduled first within detail budgets. It can correct one fresh row
  without a global forced refresh. Unknown targets cannot dispatch listing requests.
- Reed can publish descriptions with abrupt endings. Three Norton Rose Fulbright
  examples have identical endings in the visible description and current-page JSON-LD;
  retain all board-served text without inventing the continuation. The evidence helper
  exposes structured-description lengths/endings for independent completeness checks.
- FDM's displayed permanent/full-time employment metadata and a short client assignment
  in the description describe different concepts. Preserve the board employment field;
  do not infer contract employment solely from a client-engagement duration.
- 38 Degrees' reviewed Indeed role explicitly permits UK home/remote work and requires
  UK right to work. Its four-day week is labelled full-time and paid at the full stated
  annual rate; do not invent salary prorating or part-time classification.
- Indeed one-sided “up to” compensation is a null minimum plus supplied maximum, not
  a fixed range. Capital One permanent-only roles stay null for working-hours type.
  Huxley's reviewed 70000/year headline takes precedence over its conflicting prose.
- Indeed discovery salary snippets can contain a USD/EUR currency flag with no actual
  text or amount. That alone is neither compensation nor workplace evidence. Preserve
  null salary values and validate the bound job country/workplace independently.

## Lifecycle and grouping

- Discovery sightings advance last seen without pretending details were refreshed.
- Default detail interval is 24h, oldest due first, including rows absent from search.
  Failed refreshes remain due. Maintenance forcing is explicit and recorded in reports.
- Only confirmed source removals/expiry can set `removed_at`; inline-search endpoint
  failures are not confirmed listing not-found. Reappearance preserves original first seen.
- Dedupe: employer/role/location candidate index; references and distinctive text verify
  matches; contradictions reject them. Complete-link checks avoid transitive false merges.
- Oldest established canonical IDs survive merging. Wording-only edits retain identity;
  definitive conflicts split only the edited row. Unknown employers/unverified recruiter
  aliases and same-board copies without requisition evidence are conservatively unlinked.
- Synthetic pair test performance is not a general precision/recall estimate.
- Tesco/Tesco Technology LinkedIn IDs `4470379586`/`4470374657` are a strong reviewed
  real candidate: identical description/title/place, explicit shared legal employer,
  source references `209433TescoUK`/`209433Technology` and one-second posting gap.
  Live refresh now links them using a narrowly scoped recruitment-channel rule:
  verified issuer/brand, explicit legal employer, expected suffix/same numeric stem,
  exact title/concrete workplace/full description. No general aliases or arbitrary
  suffix removal. The older canonical ID survives; source hashes/first seen are stable.
- Source references are matching provenance, not exported content. Bind them to the
  current content hash in `listing_match_evidence`, update transactionally, invalidate
  feature caches on metadata changes, and ignore stale-content evidence. Missing evidence
  on a wording edit is not by itself a definitive contradiction of established identity.
- Rule version 2 matches both positives and rejects fourteen negatives in the frozen
  real corpus. It has only two positives/no holdout and is not a general precision/recall
  estimate. Further independently selected cross-board/wording-variant pairs remain open.
- Humaans LinkedIn IDs `3955668958`/`4030407849` have identical descriptions but
  different visible seniority and source references `44421-0`/`69448-0`. Retain them
  separately; common prose alone must not overrule those concrete distinctions.
- Reed Norton Rose IDs `57364884`/`57364885` share company/place/posting time and
  introductory prose but are AI engineering versus data science/engineering roles.
  Connells IDs `57147108`/`57115738` share employer/place but have platform/core-data
  duties and different references `CF00744`/`CF00810`. These are concrete real negative
  examples; common corporate prose does not justify merging distinct vacancies.

## Discovery traversal

Hidden Indeed preview nodes absent from a successfully decoded result set are not
listing observations. Reject that evidenced combination only; retain metadata-backed
hidden results and visible/no-metadata fallbacks. Suppress only unknown pending work,
never stored-job lifecycle. Recent saved source proof can repair pre-fix queues and
verified real result metadata clears the specific artefact cache.

`CRAWL_DISCOVERY=auto` avoids repeated heads when actionable queued work fills the
detail budget, but does not discard unfinished discovery. `always` rechecks heads;
`never` drains queued/due/targeted work without completing discovery checkpoints.
Twenty-five details/source at two-second HTTP pacing produced a 2m53s coordinated
batch; that is a measured sequential workflow, not an untested concurrency claim.

Follow verified Reed/Indeed source next links, restricted to same-host HTTPS `/jobs`
paths. LinkedIn uses its public guest-results endpoint after the initial full page.
Advance guest offsets by distinct IDs observed within that query/location scope.
Do not mark capped/failed/search traversals authoritative for removal.

Verified on 2026-10-09: full-page LinkedIn `start=25` and constructed Indeed `start=10`
repeated the initial ID sets. Reed's source-supplied `pageno=2` link yielded new IDs.
Indeed exposes an actual next link with `radius=25`; follow that rather than assuming
an offset-only URL is equivalent. Evidence is in the latest status note.

Follow-up verified the public LinkedIn guest-results endpoint at offset 60: 10 new
listing IDs were returned. Offsets should advance by observed IDs, not an assumed
25-item full-page count. Indeed's real next link also led to a page-two sign-in gate;
mark that traversal limited/blocked and collect public first pages across scopes instead.

Bounded four-scope tests on 2026-10-09 confirmed LinkedIn offsets 60 and 70 each add
10 IDs, but a later scope returned 429. Stop the affected source after such a block;
this does not establish safe throughput for large crawls.

Reed ignores `location=London` on the UK-wide slug. Its page declares location paths
such as `/jobs/software-engineer-jobs-in-london`; use those. The corrected captured
page has a London title/heading, location input, scoped next link and distinct IDs.

After the first Indeed pagination sign-in gate, stop later scopes at the first page
for the rest of that run. Do not count this as a source-wide bot block that prevents
public first-page or detail access. Keep the last successfully loaded search URL for
inline details. A selected job whose board identity is missing is rejected, never
filled from another result card; one such failure occurred in the broader live run.

Queries/locations are trimmed and deduplicated at configuration time. Candidate IDs
are deduplicated per source across scopes; progress/events expose overlaps and page
limits. Durable supporting tables now complement those reports (see below).

## Durable recovery policy

- Queue every real discovery candidate with its public URL and ID-bound date hint.
  Fresh complete listings and recent exclusions are pruned without requests. Successful
  details, confirmed expiry/not-found and validity rejection acknowledge the queue;
  failures/interruption retain work. Retry scheduling rotates failures behind older
  unattempted work within the existing/unknown classes. Due periodic refreshes retain
  first priority; known queued incompleteness/reappearance precedes unknown IDs.
- A page's sightings, pending candidates and next checkpoint commit together. Details
  and acknowledgement also commit together, with counters applied after commit. Source
  lifecycle reconciliation remains shared with offline fixtures; progress tables never
  manufacture source content or treat cached candidates as fresh sightings.
- Resume only unfinished source cycles with matching query/location/page-limit plans
  and age below `DETAIL_REFRESH_HOURS` (24 hours by default). Completed, changed or
  older plans start again at search heads while retaining the pending queue. A configured
  page cap remains a cap, rather than silently increasing discovery depth across runs.
- Persist only allowlisted same-source search parameters; strip session/tracking
  parameters from saved next URLs. Store prior IDs/fingerprints/URLs so guest offsets
  and loop detection survive restart. Indeed's learned sign-in pagination limit also
  survives resumption of that unfinished cycle.
- Live SIGINT validation committed Reed page one/25 IDs, exported 35 unchanged rows,
  then resumed the same cycle at page two. Two queued listings were accepted with four
  subsequent requests; 72 candidates remain pending. See `recovery-findings.md` for
  commands/evidence. This validates bounded recovery, not search completeness.

## Reproducibility isolation

- Rehearse current candidate code without committing: use a temporary Git index and
  clean checkout of an explicit runtime-file allowlist. Include uncommitted modules/
  tests, exclude credentials/local environments/captures/old exports, and pass proxy
  configuration through environment variables only.
- Use a unique Compose project/volume and fresh `rotto_test_<uuid>` database. Verify
  its exact name and zero initial public tables, build without layer cache, then use
  `make crawl` for both first and incremental live requests. Remove only the isolated
  project/volume after saving evidence; never reset live data.
- Incremental runs may legitimately add pending listings. Verify every original row's
  first-seen/hash/canonical stability, exact new-ID counts, safe removal state and fresh
  skips rather than requiring zero new jobs from an intentionally capped earlier crawl.
- Clean-source rehearsal passed on the current Docker host (base image already present).
  Both test forms passed with proxy credentials cleared; all live table fingerprints,
  export hashes, staging and HEAD stayed unchanged. A final committed remote clone
  check remains necessary during submission preparation.

## Coordinated validation and data repair

Simple title/location/word-stream agreement is not a validity grade: a seeded random
review found a GB-tagged advert explicitly requiring relocation to Australia and a
copied careers page with unrelated vacancy footer/missed between-and salary. Clear
foreign title plus mandatory relocation overrides misleading recruitment metadata;
mere overseas-market mentions do not. Parse explicit between/and pay ranges and trim
only labelled multi-vacancy footers, preserving this role's application guidance.

The wrongly imported overseas row was explicitly archived in full with identity/
content-matched source evidence in `listing_quarantine`, then excluded from assessment
jobs. This narrow invalid-import correction is distinct from ordinary crawling, live
reset or source expiry. Do not silently mark live non-UK roles source-expired.

The new holdout rejects seven unused inspected negatives and leaves one ambiguous
cross-board candidate unscored. It has no confirmed positives; precision/recall stay
null. No rule was changed to fit it. More confirmed cross-board positives remain open.

Cost rate remains unknown. Report decoded traffic, source throughput and logical
listing-fetch versus request-attempt cost units explicitly; retain null USD estimates.
Do not infer provider-billed usage/remaining allowance by subtracting decoded bytes
from the supplied 10 GB allowance. More traffic/rate information must come from the
user's supplied proxy usage/rate data.
