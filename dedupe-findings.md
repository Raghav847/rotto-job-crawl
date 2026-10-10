# Real dedupe evaluation and source evidence — 2026-10-09

## Frozen development corpus

`tests/fixtures/real_dedupe_labels.json` records sixteen manually inspected pairs:
two duplicates and fourteen nonduplicates. `real_dedupe_pairs.json` freezes the
twenty-six referenced source listings and their public employer-reference evidence.
It contains required listing fields, not source scripts, cookies or credentials.
The freezer requires captured title, location and complete description-word agreement.

Positive evidence includes the previously verified Leidos Bristol cross-board copy
and the Tesco/Tesco Technology recruitment-channel copy. Negative cases cover
different seniority/requisitions despite identical prose, platform versus core-data
duties, applied AI versus data science, manager versus engineer, named business teams,
different client engagements and unrelated employer/technology programmes.

Commands:

```sh
uv run --locked --offline python -m crawler.dedupe_review --freeze --report output/reviews/real-dedupe-baseline.json
uv run --locked --offline python -m crawler.dedupe_review --report output/reviews/real-dedupe-updated.json
```

Evaluation reads frozen files only and never fetches their public URLs. Freezing
requires local DB/captures; the committed frozen corpus does not.

| Result | Previous matcher | Rule version 2 |
| --- | ---: | ---: |
| True positives | 1 | 2 |
| False negatives | 1 | 0 |
| False positives | 0 | 0 |
| True negatives | 14 | 14 |
| Precision on this set | 1.0 | 1.0 |
| Recall on this set | 0.5 | 1.0 |

This is a small deliberately selected development set, with only two positives and
no independent holdout. It is not a general precision/recall estimate. More real
cross-board positives, wording variants and independently selected difficult cases
remain necessary.

## Source-reference provenance

The LinkedIn adapter reads an employer reference only from the single identity-bound
current-page JobPosting. Its identifier issuer must match both the declared hiring
organisation and visible stored company. A value equal to the board ID, or explicitly
marked `JobId`, is not interpreted as an employer reference. Reed board IDs remain
board identities, not cross-board requisitions.

`Listing.matching_evidence` carries the small verified reference through the same
observation/reconciliation service used by live crawls and offline fixtures.
`listing_match_evidence` binds it to the job's current content hash. It is supporting
matching provenance, excluded from required exported fields and content hashes.
Feature caches include an evidence fingerprint so metadata-only changes re-evaluate
grouping; stale-content evidence is ignored. Reference writes and canonical changes
are transactional, and delayed observations cannot replace newer references.

## Scoped Tesco matching

The public source identifiers are `209433TescoUK` and `209433Technology`. Both pages
explicitly say applicants will be employed by **Tesco Stores Limited**, and the
complete descriptions, advertised title and Welwyn Garden City workplace agree.

The normalizer recognizes only the verified Tesco recruitment channels, bound to:

- LinkedIn source, matching declared issuer and the relevant Tesco advertiser brand.
- The explicit named legal-employer declaration.
- The same numeric requisition stem with the expected channel suffix.

New cross-brand merging additionally requires exact normalized title tokens,
the same concrete workplace, complete-description fingerprint equality and enough
role text. It does not establish general company aliases or strip arbitrary suffixes.
Other employer references use their exact issuer-scoped value. Conflicting references,
roles and workplaces reject matching; complete-link grouping and oldest established
canonical IDs remain in force.

Tests reject missing references/legal declarations, wrong issuers, different stems,
seniority, role text, workplaces, broad remote scopes and unverified brands. They also
verify metadata-only merging with zero lifecycle changes, unchanged hashes/first seen,
reference-change cache invalidation and splitting, wording edits with omitted evidence,
delayed input and transaction rollback.

## Live canonical verification

```sh
CRAWL_SOURCES=linkedin CRAWL_QUERIES="Tesco Identity" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=10 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS=linkedin:4470379586,linkedin:4470374657 CRAWL_FORCE_REFRESH=0 make crawl
```

Evidence: `output/runs/20261009T191325Z-f17e1383/`.
Three successful requests, no blocks, 938,661 decoded bytes. Both details refreshed;
the two references were persisted and the duplicate linked with reason
`scoped_recruitment_channel`. The older Tesco canonical ID
`4ad628b5-d616-53a5-b935-48e63f8c5a30` survived. SQL checks confirmed both original
first-seen timestamps/content hashes and unchanged Leidos grouping.

All new/changed/removed lifecycle counts were zero. Rule-version migration indexed
82 existing rows without detail requests. Exports now contain **82 live listings /
80 canonical jobs / two linked duplicates**. The three board counts remain 28 Indeed,
26 LinkedIn and 28 Reed. Pending queues are 57 Indeed, 162 LinkedIn and 97 Reed.

`docker compose build crawler && make test` passed **102 tests**, all three supplied
fixture runs and idempotent replays. Export verification passed for all 82 rows,
hashes/counts and three logged requests. `git diff --check` passed.

Next: investigate invalid Indeed discovery selections and tune practical coverage/
efficiency while extending the real labelled corpus. Final clean committed-clone,
README, cost assumptions, Loom, collaborator access and submission checks remain.
