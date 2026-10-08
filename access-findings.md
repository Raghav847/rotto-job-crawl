# Initial access findings

Observed on October 7, 2026 using the supplied UK residential proxy and `curl_cffi` with Chrome impersonation. These are small feasibility samples, not a production accuracy or coverage evaluation.

## Initial diagnostic request budget

| Run (UTC) | Purpose | Requests | Blocked | Response bytes |
| --- | --- | ---: | ---: | ---: |
| 23:18:14 | All-board discovery and first available detail | 5 | 1 | 1,356,083 |
| 23:19:14 | Capture Indeed challenge evidence | 1 | 1 | 28,181 |
| 23:20:01 | Inspect a second Reed result | 2 | 0 | 689,701 |
| **Total** | | **8** | **2** | **2,073,965** |

Bytes are decoded response-body sizes, approximately 2.07 MB in total, not measured proxy-billed traffic. Cost cannot yet be calculated credibly because the assessment does not give a USD/GB rate.

Local request logs, summaries, and HTML are under `output/diagnostics/<UTC-run>/`, excluded from Git. Each request attempt is logged; automatic redirects/retries are disabled, with up to four explicitly logged same-host redirect attempts per fetch. Each source fetches at most one discovery page and one selected detail page.

## Verified live persistence milestone

The production entry point now runs discovery, full-detail parsing, shared reconciliation, and exports. HTTP logs and optional page samples are under `output/runs/`; the earlier diagnostic remains available through `CRAWL_MODE=probe make crawl`.

| Run (UTC) | Detail budget per source | Requests | Blocked | Response bytes | New / changed / removed |
| --- | ---: | ---: | ---: | ---: | --- |
| 23:56:20 | 3 | 9 | 1 | 2,554,902 | 5 / 0 / 0 |
| 23:58:04 | 0 (discovery-only verification) | 3 | 1 | 762,094 | 0 / 0 / 0 |

- Stored three LinkedIn listings: JPMorganChase in Glasgow, Admiral Money in Cardiff, and Experian in Nottingham.
- Stored two Reed listings: IBM SIXworks Limited in Taunton and Cheltenham. The visible locations are preserved, including counties, rather than replaced with JSON-LD's broader regions.
- Rejected the Reed training-course advert, whose visible salary metadata says “Training Course”.
- Full stored descriptions range from 3,782 to 5,773 plain-text characters in this small sample.
- The second run advanced last seen without requesting details or changing first seen, content hashes, or lifecycle counts.
- `crawler.verify_exports` checked all five rows against Postgres, recomputed content hashes, and matched request/status/block counts to logs for both runs.
- Indeed returned HTTP 403 in both runs; reports accurately show zero Indeed listings and partial coverage.
- Offline verification now includes the three public fixture runs with replays and 28 additional parser, fetching, reconciliation, and pipeline tests.

Across the completed initial diagnostics and these two live runs, measured decoded bodies total 5,390,961 bytes, approximately 5.39 MB. This excludes the interrupted browser experiment and is not proxy-billed traffic. Costs remain unknown until a USD/GB rate is supplied.

## LinkedIn

- Discovery: `https://www.linkedin.com/jobs/search/?keywords=software%20engineer&location=United%20Kingdom` returned HTTP 200 with public listing links.
- Detail: `https://uk.linkedin.com/jobs/view/software-engineer-iii-java-at-jpmorganchase-4447742577` returned HTTP 200.
- Sample: JPMorganChase, Software Engineer III - Java, Glasgow, Scotland, United Kingdom.
- Visible description selector: `.show-more-less-html__markup`; 5,789 plain-text characters in this sample.
- JobPosting JSON-LD supplies company, logo, GB location, exact posting date, employment type, and a description. Salary is absent in this sample.
- **Identity trap:** JSON-LD `identifier.value` is `210773394`, whereas the board listing ID is `4447742577`. Use the board ID from the requested listing URL and verified page metadata, not an assumed meaning of the generic identifier.
- JSON-LD and visible-description text lengths differ. Compare their actual content before selecting the production description source.
- Detail pages link to related jobs. Their first job link is not the identity of the current page.
- Remaining work: pagination, request/block behaviour over multiple pages, field-level extraction, logo entity decoding, and reliable refresh signals.

## Reed

- Discovery: `https://www.reed.co.uk/jobs/software-engineer-jobs` returned HTTP 200 with listing links.
- First detail: `/jobs/trainee-software-developer/57302732` returned HTTP 200 and a full description, but promotes a training programme with a job guarantee. Flag for exclusion/review rather than automatically count it as a real current vacancy.
- Second detail: `https://www.reed.co.uk/jobs/software-engineer/57336545` returned HTTP 200.
- Second sample: IBM SIXworks Limited, displayed title Software Engineer, Taunton; description describes a QA Test Infrastructure Engineer working on site in Somerset. Preserve the board's displayed title rather than rewriting it from the description.
- Full description: 4,836 plain-text characters including the “Full job description” heading; strip presentation headings in the production parser.
- JobPosting JSON-LD identifies source job `57336545`, GB location, posting date, and employment types `FULL_TIME` and `CONTRACTOR`; salary is absent for this listing. Resolve the single `work_type` value against the visible source contract information.
- The training listing had salary values in JSON-LD. Structured salary availability is not proof that a page represents a valid job.
- Detail pages contain related job links; use verified current-page identity rather than the first matching link.
- Remaining work: company logo extraction, work-type normalization, pagination, training-ad filtering, and refresh signals.

## Indeed

- UK search returned HTTP 403 in both attempts through the supplied proxy.
- Saved response contains “Additional Verification Required”, “Please enable JavaScript to complete the security check”, and Cloudflare managed-challenge markup.
- Chrome-impersonated HTTP alone did not provide access in these attempts. No job content or removal evidence was obtained.
- **Next experiment:** one bounded browser-based public-page request using the same permitted proxy, logging all requests and limiting bandwidth. Observe whether normal JavaScript execution yields a page or remains blocked; do not use accounts or CAPTCHA-solving services.

## Environment and open inputs

- Available locally: Python 3.14.2, `uv`, Docker 28.3.0, and Docker Compose 2.38.1. Docker daemon responded successfully.
- Dependencies are pinned in `pyproject.toml` and `uv.lock`.
- Proxy credentials are in ignored local `.env`, loaded into environment configuration; `.env.example` contains placeholders.
- The version-1 lifecycle fixture was subsequently supplied and saved at `tests/fixtures/lifecycle.json`. It uses discovery/detail/removal observations, an explicit observation clock, exact expected row sets, prior-run hash references, and a second idempotent application of every run. Its URLs are synthetic and must never be fetched.
- A browser-based Indeed experiment was attempted after the HTTP probes, but a local filesystem permission error interrupted page capture, cleanup, and final request accounting. The HTTP totals above exclude this interrupted experiment. The browser helper needs recovery and verification before drawing access conclusions.

## Next implementation decisions

1. Run the bounded Indeed browser experiment; keep LinkedIn/Reed on lightweight HTTP unless later evidence requires a fallback.
2. Broaden field-by-field review and source-layout regression samples for the working LinkedIn/Reed parsers.
3. Add measured cross-board matching to the stable per-listing canonical IDs.
4. Expand discovery only after accuracy checks, using the existing refresh policy and request/time budgets to measure efficiency.
