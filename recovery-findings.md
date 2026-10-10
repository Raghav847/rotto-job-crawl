# Durable recovery verification — 2026-10-09

## Policy and transaction boundaries

Three supporting tables retain work without changing the required jobs schema:

- `pending_candidates`: public source IDs/URLs, exact source-date hints, first/last
  discovery, attempted scheduling and forced detail refresh after reappearance.
- `crawl_progress`: current source cycle/plan hash, start/completion and learned
  Indeed pagination sign-in limitation.
- `discovery_checkpoints`: each query/location's next page/URL, prior ID set, page
  fingerprints and visited URLs. Saved URLs strip session/tracking parameters.

A successful discovery page commits real sightings, pending candidates and its next
position atomically. A successful detail commits shared reconciliation and queue
acknowledgement atomically, then updates report counts. Explicit expiry, confirmed
not-found and validity rejection also acknowledge their queue entries. Failed details
remain pending. Queue replay alone never advances `last_seen_at` or supplies removal
evidence. Fresh complete rows/recent exclusions are pruned without detail requests.

Unfinished source cycles resume when query/location/page-limit plans match and the
cycle is younger than the refresh interval (24 hours by default). Completed, changed
or older plans restart discovery at search heads while retaining pending work. Search
caps are never interpreted as authoritative coverage or removal evidence.

Due stored refreshes retain priority. Queued known incompleteness/reappearance then
precedes unknown IDs. Within those classes, failed work rotates behind older
unattempted work. ID-bound date hints survive scope changes and request-budget caps.

## Offline verification

`docker compose build crawler && make test` passed **88 tests** and all three supplied
lifecycle fixture runs/idempotent replays. Added tests cover:

- Resuming a committed page after a request-budget exception without refetching it.
- Python interruption before/after successful detail acknowledgements.
- Pending work surviving changed query scopes without fabricating fresh sightings.
- Atomic rollback if checkpoint or acknowledgement writes fail.
- ID-bound dates surviving queueing and absence from subsequent search pages.
- Changed/stale plan invalidation, safe saved URLs and failed-work retry rotation.
- Limited-source reporting when discovery ends but detail work remains queued.
- Durable HTTP request starts and counted completion after an in-flight interruption.

All tests use freshly created UUID-named databases. Live data was preserved.

## Live process interruption and recovery

Started through the required command:

```sh
CRAWL_SOURCES=reed CRAWL_QUERIES="data engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=3 CRAWL_MAX_DETAILS=2 CRAWL_MAX_REQUESTS=20 CRAWL_MAX_SECONDS=180 CRAWL_REQUEST_DELAY=10 CRAWL_SAVE_PAGES=1 make crawl
```

Sent SIGINT to the crawler's Python process eight seconds after launching it:

```sh
docker exec "$container_id" pkill -INT -f '^/app/.venv/bin/python[^ ]* -m crawler.run$'
```

Interrupted evidence: `output/runs/20261009T014538Z-1ddef7be/`.
The crawler exited **130**, reported `interrupted`, and exported all **35 unchanged
rows** with zero lifecycle transitions. One successful request committed **25 pending
IDs** and a page-two checkpoint. The saved URL contained keyword/page parameters and
no session parameter. The source cycle remained unfinished.

Reran the same scope/page limit with `CRAWL_REQUEST_DELAY=1` (the remaining settings
were unchanged). Resume evidence: `output/runs/20261009T014612Z-1e09c794/`.
The report confirms `resumed_cycle: true`, the same cycle ID, and one previously
fetched page. Request evidence starts at page two; only **two discovery pages and two
details** were requested. Reed returned 74 distinct IDs across the complete capped
three-page cycle. Both details were accepted as new UK listings:

- `reed:56212211`: Data Engineer, London.
- `reed:57115738`: Data Engineer, Milton Keynes, Buckinghamshire.

The run used **four requests**, no blocks, 1,446,817 decoded bytes, two new rows,
zero changed/removed rows, and left **72 pending candidates**. The database/export
now has **37 live listings** (8 Indeed, 16 LinkedIn, 13 Reed), **36 canonical jobs**,
and one linked duplicate. These two newly stored listings have captures but are
outside the prior documented field-by-field accuracy batches.

`docker compose run --rm --no-deps crawler uv run --locked --offline python -m crawler.verify_exports`
passed after both runs, checking DB equality, hashes/counts and one/four logged
requests respectively. SQL checks confirmed the unfinished/finished cycle state,
queue counts and retained checkpoint. Captures/logs stay in ignored run folders.

Next: clean-checkout/fresh-database reproducibility rehearsal and broader independent
accuracy review. This is a bounded SIGINT recovery exercise, not a complete-search
or large-scale throughput claim.
