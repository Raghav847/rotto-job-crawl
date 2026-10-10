# Bounded discovery verification — 2026-10-09

## Implemented behavior

- Query/location partitions are configurable with comma-separated `CRAWL_QUERIES`
  and `CRAWL_LOCATIONS`; duplicate configuration entries are removed.
- Reed/Indeed follow source-declared, same-host HTTPS next links on `/jobs` paths.
- LinkedIn starts with full search, then uses the public guest-results endpoint.
  Offsets advance by distinct IDs observed within the current scope.
- Repeated result sets and URL loops terminate traversal. Overlapping IDs across
  scopes receive at most one detail task per source/run; fresh details are skipped.
- Per-scope reports show pages, unique IDs and termination reason. Search coverage
  never provides removal evidence.
- An Indeed sign-in pagination gate limits later scopes to public first pages for
  that run. It does not prevent further public discovery/detail selection.

## Live evidence

Exact commands and export verification are recorded in `knowledge-base/status.md`.

| Run | LinkedIn IDs | Reed IDs | Indeed IDs | Requests | Lifecycle |
| --- | ---: | ---: | ---: | ---: | --- |
| `20261009T011254Z-5b554641` — two queries, two locations, two pages, five details/source | 197 | 102 | 56 | 64 | 12 new, zero changed/removed |
| `20261009T011524Z-6be07a73` — same scopes, three pages, no details | 208 | 266 | 52 | 51 | Zero transitions |

These are discovered source IDs, not validated stored-job counts. The first run
accepted four new listings per source, rejected one ambiguous UK-eligibility listing
and one training advert, and safely rejected one Indeed missing-identity detail.
The database/export now has 8 Indeed, 16 LinkedIn and 11 Reed live listings; 34
canonical jobs and one linked duplicate. Captures/logs remain in ignored run folders.

Reed ignored `location=London` on its UK-wide slug: heading/location controls stayed
unscoped and next links omitted location. The captured page declares the
`/jobs/software-engineer-jobs-in-london` path. Following that pattern produced a
London heading/input and scoped next links, verified in the follow-up.

LinkedIn's initial search returned 60 IDs, then guest offsets 60 and 70 each returned
10 additional IDs. A later scope returned 429; the crawler stopped the affected
source and preserved stored data. Indeed's page-two next link still reached sign-in;
all three later first-page scopes remained accessible without another page-two attempt.

Both exports matched Postgres, content hashes, canonical counts and request logs.
The corrected implementation passes 74 tests plus all three lifecycle fixture runs
and idempotent replays. This is bounded discovery evidence, not a general accuracy
or large-scale throughput claim. Candidate queues, durable traversal checkpoints,
larger field-by-field review and interruption recovery remain next work.
