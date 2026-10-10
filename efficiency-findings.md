# Indeed resource-efficiency review

## Measured comparison

Both runs refreshed the three stored Indeed listings (Rolls-Royce, Leidos and Standard Life), using the same public-pane extraction path and supplied proxy.

| Measure | Earlier successful run | Lean resource-policy run |
| --- | ---: | ---: |
| Network request attempts | 224 | 24 |
| Decoded response-body bytes | 12,736,170 | 6,314,831 |
| Successfully refreshed detail listings | 3 | 3 |
| New / changed / removed | 0 / 0 / 0 | 0 / 0 / 0 |

Approximately **89% fewer requests** and **50% fewer decoded bytes** for the same three-detail review workload. This is a small before/after observation, not a guaranteed production rate: proxy IPs, challenge overhead and source responses can vary. Body bytes are not proxy-billed traffic.

Baseline log: `output/runs/20261008T070203Z-3817933d/indeed-browser/requests.jsonl`.
Lean log: `output/runs/20261008T193656Z-3d856e06/indeed-browser/requests.jsonl`.
Ignored captures/logs are generated locally; `crawler.browser_metrics` summarizes them offline.

## Why the original run was expensive

- The successful baseline downloaded 164 scripts from `c03.s3.indeed.com`, about 5.39 MB.
- Frontend, header/footer and consent bundles were requested again on each navigation.
- Consent scripts and configuration requests consumed further traffic.
- Another review reached its limit with 310 Indeed attempts, including pending/aborted resources; the partial run preserved stored rows.

The HTML contains the complete selected job pane and serialized job/branding metadata. Frontend hydration and consent/tracking interfaces are not needed to extract those fields. Managed security checks still need their scripts, frames and requests.

## Implemented policy

- Preserve documents, public data requests, Cloudflare resources and Indeed's `/cdn-cgi/` endpoints.
- Preserve Cloudflare-specific signaling on `t.indeed.com`.
- Skip observed frontend CDN bundles, general telemetry, OneTrust UI calls and background ping/websocket channels.
- Continue preventing image/font/media downloads and bulky Indeed stylesheets.
- Capture server-rendered content sooner; do not wait for a blocked logo image to load. Its URL comes from source branding JSON.
- `INDEED_RESOURCE_POLICY=baseline` restores earlier loading for comparisons. Default is `lean`.

## Accounting and validation

Request intent is logged before routing. A request consumes a network slot when dispatched; locally skipped resources are recorded separately. Automatic redirects remain accounted for, including a rare in-flight redirect crossing the limit. Asset-budget exhaustion no longer closes an otherwise readable page prematurely.

Tests check the resource allow/skip policy, security-resource preservation, no logo downloads and budget reservations. Existing description, salary, logo, identity, lifecycle and dedupe checks pass. The lean live refresh kept stored content hashes unchanged; export verification matched Postgres and the request log.

### Subsequent all-board check

A bounded run using the lean policy accepted one new listing from each board in **23 total request attempts**, with about **5.27 MB of decoded bodies**. It included a transient proxy tunnel failure and security-check responses, all logged; each source still completed its selected detail extraction without a parser failure.

The latest export contains **4 Indeed, 12 LinkedIn and 7 Reed live listings** (23 source listings, 22 canonical jobs, one linked duplicate). Source limits intentionally report partial coverage. This run also verifies new-listing extraction under the lean policy, beyond refreshing the three known Indeed examples.

Logs: `output/runs/20261008T210556Z-95e3a477/requests.jsonl`. The expanded suite contains 65 tests, plus the supplied lifecycle fixture and its replays. Export verification checks persisted rows, hashes, canonical counts and request accounting.

## Remaining work

- Document responses and managed-check traffic now dominate bytes: about 4.81 MB of Indeed documents in the lean run.
- Investigate lighter public detail/discovery routes and richer checkpoints from observed source behaviour.
- Repeat measurements on larger reviewed samples before selecting final budgets.
- Obtain the proxy USD/GB rate for cost estimates.
