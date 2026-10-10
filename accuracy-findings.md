# Initial field-level accuracy review

## Scope and method

Reviewed all 20 stored listings: 3 Indeed, 11 LinkedIn, and 6 Reed. This is a small development census, not a random sample or an estimate of general accuracy. We still need at least 25 reviewed listings per board as coverage expands.

`crawler.accuracy_review` inventories captured source evidence independently of the listing parser: visible title/location, employer, logo markup, employment metadata, structured posting date/country, compensation fields, and description excerpts. It also compares description word streams after presentation-heading removal. Records and raw evidence are kept under ignored `output/reviews/`; this report contains the conclusions.

Fresh live review runs re-fetched all 11 stored LinkedIn listings, all 6 Reed listings, and all 3 Indeed listings through `make crawl`. One LinkedIn run encountered HTTP 429 and stopped; a slower follow-up completed the outstanding checks. Good rows were preserved throughout.

## Findings and corrections

### Five LinkedIn salary records were inaccurate

- Client Server's Backend Software Engineer listing showed **£100,000.00/yr–£130,000.00/yr**, also confirmed by JSON-LD. The old parser stored 100000 for both bounds and no period. It now stores **100000 / 130000 / year**.
- Four Leidos listings explicitly supplied **£61,500–£78,800** in their descriptions, but the old parser only inspected dedicated compensation fields or JSON-LD. Those rows now store the stated bounds.
- The Leidos descriptions do not state a pay period alongside those amounts, so LinkedIn's `salary_period` remains null. Indeed separately states “a year” for its copy; that does not authorize guessing a missing LinkedIn period.
- `/yr` and `/hr` separators within a range are now supported. Annual leave is not interpreted as an annual salary period.
- Description fallback only accepts explicit salary/pay statements. Free shares, bonuses, company assets and training costs are excluded; inconsistent numeric statements remain unresolved rather than guessed.

The corrections were applied through fresh live observations and the shared reconciliation code, preserving original first-seen timestamps and canonical IDs.

### One description had joined inline words

The Bristol LinkedIn Leidos copy contained adjacent formatting tags that produced strings such as `caninspirechange` and `leidosempowerspeople`. Plain-text conversion now preserves word boundaries while retaining paragraphs and removing page controls/styles.

All 20 stored descriptions now match the captured description word streams under the independent formatting-sensitive comparison. This checks completeness/readability; it is not a validity or accuracy percentage.

### Indeed could not refresh a selected job absent from search cards

The public pane correctly identified Rolls-Royce's listing, but it was absent from the current search-result metadata array. The parser previously rejected it despite receiving a full description.

It now reads the public selected-view payload, requires its explicit `jobKey` to match the pane/requested ID, and uses **`jobCountry`**, not the page's country setting. Logged-in payloads are rejected. When this identified pane omits a previously verified posting date, that date is preserved; new listings without source date data remain null. The fresh review then successfully refreshed all three existing Indeed rows.

## Other reviewed fields

- Visible titles and locations agreed with stored values for all 20 captures. Source differences are preserved: for example, Reed displays “Software Engineer” while its description calls the role a QA Test Infrastructure Engineer.
- Every reviewed workplace has explicit GB source evidence; there are no ambiguous remote-only listings in this live sample.
- Employer names, employment metadata and posting dates agreed with source evidence. “Contract, full-time” maps to contract; “permanent” alone does not establish full-time hours.
- Logo URLs agree with source-served logo markup/branding data. The Standard Life square logo remains distinct from its wide banner. No logo image is downloaded.
- Non-numeric “Competitive salary” and “Salary negotiable” remain null unless an explicit pay statement is available elsewhere in that listing.
- Standard Life's headline range (70000–80000/year) differs from its description's “from 75000”. The dedicated board compensation field takes precedence; this source discrepancy is recorded rather than rewritten.
- Job descriptions retain employer-provided requirements and application guidance, while excluding site navigation, recommendations and unrelated salary information.

## Verification and outstanding work

Regression tests cover repeated-unit salary ranges, explicit description pay, benefit/asset false positives, compensation precedence, inline text boundaries, selected-view identity/country evidence, and explicit maintenance refresh. Existing lifecycle/dedupe tests also run.

`CRAWL_FORCE_REFRESH=1` is an explicit maintenance/review override; the default remains the documented 24-hour policy. Reports record whether the override was used.

Outstanding: expand independently reviewed live samples to at least 25 per board, include real UK-eligible remote and hidden-employer cases, and review more source layouts. Indeed's resource-heavy review exhausted one request budget, confirming that browser-traffic optimization is the next priority. No 95%+ general accuracy claim is made from this sample.

## Follow-up: twelve new listings — 2026-10-09

Reviewed the four new listings per board added in
`output/runs/20261009T011254Z-5b554641/`. The independent inventory now supports
`--run` and `--ids`, records discovery-date evidence separately, and writes readable
full-description files under ignored `output/reviews/`. Full descriptions, identity,
UK evidence, employer/branding, employment, compensation and posting dates were checked.
This adds twelve distinct listings to the earlier twenty-listing review, for a total
of 32 reviewed listings (7 Indeed, 15 LinkedIn, 10 Reed); three other stored listings
remain outside these documented review batches.

| Source ID | Employer / workplace | Finding |
| --- | --- | --- |
| `linkedin:4470374657` | Tesco Technology / Welwyn Garden City | Fields agree; bonus percentage does not supply a salary amount. |
| `linkedin:4449078328` | HP / Cambridge | Fields agree; employer's opening “Description -” text is retained. |
| `linkedin:4449465893` | Trustonic / Winnersh | Fields agree; hybrid office attendance is explicit, numeric salary absent. |
| `linkedin:4296369615` | DoorDash / London | Fields agree; source's September 2025 posting date is retained. NYC hiring-policy prose is not workplace evidence. |
| `reed:57321518` | Matchtech / Luton | Contract, £78/hour agrees with headline/structured data and umbrella wording. |
| `reed:57424368` | Matchtech / Cowes | Contract, £73.68/hour follows headline; description also offers £54.57/hour PAYE. Do not conflate the two pay bases into a range. |
| `reed:57411163` | Matchtech / Stockport | Full-time, £75,000–£90,000/year agrees; description offers several UK offices. |
| `reed:57435600` | FDM Group / London | Contract agrees; salary negotiable stays null. This is a live client engagement, not a training advert. |
| `indeed:1c2b4cc4f74044cd` | Redhorse International / London SE1 | Corrected missing posting date to 2026-05-12T05:00:00Z. |
| `indeed:0ee5965a1444f71a` | Redhorse International / Manchester Central | Corrected missing posting date to 2026-05-12T05:00:00Z; remains separate from London copy. |
| `indeed:ef4b93145626d5c7` | VACAC / Cambridge | Corrected missing posting date to 2026-08-07T05:00:00Z; full-time, £35,000–£40,000/year agrees. |
| `indeed:a471df05393f6006` | HippoDigital / Liverpool L1 | Corrected missing posting date to 2026-10-08T05:00:00Z; full-time, £57,500–£72,000/year agrees. £8,000 relocation support is not salary. |

### Confirmed defect: date evidence lost between discovery and detail

All four new Indeed selected panes omitted dates despite their earlier search cards
providing exact `pubDate` values. The crawler used only the current detail-page cards,
so switching search scopes lost those dates and stored null.

Discovery candidates now carry exact dates tied to their own card ID. A successful
identity-verified detail observation can use that date when the detail pane omits it.
Existing known dates remain stable; current explicit detail dates take precedence.
Known missing-date enrichment is prioritized after due refreshes and before new
detail work. Discovery alone and failed details do not rewrite content.

Two live runs corrected all four rows via shared reconciliation, without new listings
or removals. SQL checks confirmed original first-seen timestamps/canonical IDs.
The first refreshed all eight Indeed rows and corrected two dates; narrow employer
queries then corrected the remaining two. Exact commands/evidence are in
`knowledge-base/status.md`. Latest exports retain 35 live rows and 34 canonical jobs.

### Review-tool correction and other conclusions

The initial comparison falsely flagged HP's description because its heading-removal
regex stripped the word “Description” from employer prose. It now strips only
standalone presentation-heading text. All twelve stored descriptions agree with
the independent word streams; complete descriptions were also read for unrelated
page text, pay statements and eligibility contradictions.

All twelve have explicit GB workplace metadata. Indeed's four null logo URLs are
supported by absent logo containers and null `companyImagesModel.logoUrl` values.
LinkedIn/Reed stored logo URLs agree with their visible source-logo markup. Board
advertiser names are preserved, including recruiter names; no hidden client is guessed.

Verification: `docker compose build crawler && make test` passes 76 tests and all
three supplied fixture runs/replays. Tests cover ID-bound date hints, invalid dates,
enrichment priority, failed-detail preservation and successful lifecycle/hash handling.
Export verification passes after both correction runs. Larger independent random
samples, genuinely remote UK eligibility and hidden-employer layouts remain open.

## Follow-up: remaining five stored listings — 2026-10-09

Reviewed the five rows outside the preceding batches using saved public captures and
complete readable descriptions. All source-field values agree; no runtime parser or
stored-content correction was required. Combined documented coverage now includes
**all 37 stored listings: 8 Indeed, 16 LinkedIn and 13 Reed**. This is a development
census, not a random sample or a general accuracy estimate; dedupe quality is assessed
separately and a new candidate is recorded below.

| Source ID | Employer / workplace | Reviewed conclusion |
| --- | --- | --- |
| `indeed:9f0d5e9babff5535` | DFYNE / Uddingston | Full-time; “from £85,000/year” correctly stores minimum 85000 and null maximum. No declared logo. Exact September 9 source date is preserved when the later pane omits it. |
| `linkedin:4470379586` | Tesco / Welwyn Garden City | Source title, logo, full-time status and exact posting date agree. Numeric salary absent; bonus percentage is not salary. |
| `reed:57421313` | Kingdom People / Portsmouth | Source headline “Senior Software Engineer” retained despite more-specific automation/production-support prose. £58,033/year is explicit in headline/JSON-LD. Recruiter name retained without guessing its hidden client. |
| `reed:56212211` | FDM Group / London | Genuine returners employment listing: explicitly commits to at least two years of full-time employment and consultant/client assignments. Training/upskilling wording does not make this a tuition-only advert. Negotiable salary remains null. |
| `reed:57115738` | Connells Group HQ / Milton Keynes | Full-time, £45,000–£55,000/year, advertiser logo and exact posting date agree. Hybrid office attendance and UK right-to-work are explicit. Description reference `CF00810` is retained. |

All five have explicit GB workplace evidence and complete matching description word
streams. Source descriptions were also read for unrelated page text, compensation
ambiguity, employment validity and eligibility contradictions. FDM's December 2025
posting date is retained: a recent successful live detail capture exists and age alone
is not expiry evidence. DFYNE's prior identity-matched search card supplies
`2026-09-09T05:00:00Z`, while its later pane has null date/branding-logo values.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --ids indeed:9f0d5e9babff5535 linkedin:4470379586 reed:57421313 reed:56212211 reed:57115738`.
DFYNE's older date was checked with
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T011254Z-5b554641 --ids indeed:9f0d5e9babff5535`.
Per-row decisions/capture paths are in ignored `output/reviews/five-listing-decisions.json`.
The helper now exposes structured source identifiers for independent matching review.

### Newly inspected dedupe candidate

`linkedin:4470379586` (Tesco) and `linkedin:4470374657` (Tesco Technology) have identical
full descriptions, role and Welwyn Garden City workplace. Both explicitly name Tesco
Stores Limited as the legal employer. Their source identifiers are `209433TescoUK`
and `209433Technology`; timestamps differ by one second. They currently have separate
canonical IDs. This is a strong candidate for the real dedupe corpus/matching-policy
review; it does not establish a general brand alias or justify removing arbitrary
reference suffixes. Matching improvements should use scoped corroborating evidence
and test nearby negative pairs.

### Next bounded expansion

Reviewed counts leave **17 Indeed, 9 LinkedIn and 12 Reed** additional listings needed
to reach 25 per board. Collect/review small source-specific batches with saved captures:
LinkedIn two-page traversal and a 12-detail budget; Reed overlapping software/data
scopes plus its existing pending queue with a 15-detail budget; Indeed public first
pages across UK/London/Manchester software/data scopes with a 22-detail budget.
Keep request/time caps, default freshness and stop-on-block behavior. These are
development budgets, not guaranteed accepted counts. Review each new batch before
raising limits further; retain pure-remote/hidden-employer and dedupe-corpus goals.

## LinkedIn expansion: ten new reviews — 2026-10-09

Command: `CRAWL_SOURCES=linkedin CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=12 CRAWL_MAX_REQUESTS=40 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 make crawl`.
Evidence: `output/runs/20261009T021040Z-a7889f70/`. Two pages returned 70 IDs;
12 fresh details were skipped, ten new rows accepted and two UK-ambiguous listings
rejected. 14 requests, zero blocks, 4,062,109 decoded bytes, zero changes/removals.
All ten accepted listings have captured full descriptions and independent field review.

| Source ID | Employer / workplace | Reviewed conclusion |
| --- | --- | --- |
| `linkedin:3955668958` | Humaans / London | Full-stack, full-time, in-person role; no numeric salary. Exact 2024 source date retained. Funding is not salary. |
| `linkedin:4030407849` | Humaans / London | Senior full-stack role; no numeric salary. Similar prose to the other Humaans listing does not override different title seniority and source references. |
| `linkedin:4285959027` | Zopa Bank / London | Full-time; two/three London-office days per week. Foreign working allowance is a benefit, not a different workplace. No salary amount. |
| `linkedin:4393533375` | Fortinet / London | Full-time, explicitly office-based in Moorgate. Description's final empty heading is source text, not crawler truncation. No salary amount. |
| `linkedin:4401592205` | Runna / London | Full-time hybrid; £85,000–£95,000/year agrees across headline, JSON-LD and prose. Funding/stock incentives are separate. |
| `linkedin:4412048387` | Sony Interactive Entertainment / London | Full-time and explicit London/GB metadata; employer-served logo and exact date agree. No salary amount. |
| `linkedin:4414737700` | Clearwater Analytics / London | Full-time; board employer retained despite CWAN/Beacon names in prose. No salary amount. |
| `linkedin:4425784558` | Epredia / Runcorn | Full-time hybrid; description explicitly confirms Runcorn, UK. Source headline retained; no salary amount. |
| `linkedin:4434022510` | Taktile / London | Full-time London/GB role; UK regional employment entity is described. Global remote-team wording does not replace workplace metadata. No salary amount. |
| `linkedin:4437559548` | Wise / London | One salary defect corrected using corroborating source wording; now 111000/145000, period null. Full employer-provided repeated paragraphs retained. |

### Salary defect and correction

Wise's page says both **“£111,000 - £145,000k”** and **“111K - 145K GBP”**. The parser
previously ignored GBP-text amounts and interpreted the first maximum literally as
145 million. It now supports explicit GBP prefix/suffix notation. A comma-formatted
amount plus `k` is interpreted without redundant thousands only when another explicit
clean salary statement corroborates that exact alternative. There is no guessed
salary ceiling; unresolved conflicting statements remain null. Neither Wise statement
provides a pay period, so it remains null.

Added `CRAWL_REFRESH_IDS` for bounded targeted maintenance of existing stored IDs.
This targets a selected fresh listing before ordinary detail work while preserving
the normal periodic-refresh policy for routine runs. Unknown IDs cannot cause a
listing request; targets must belong to configured sources and respect detail caps.

Correction command:
`CRAWL_SOURCES=linkedin CRAWL_QUERIES="Wise Account Sharing" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=1 CRAWL_REFRESH_IDS=linkedin:4437559548 CRAWL_FORCE_REFRESH=0 CRAWL_MAX_REQUESTS=10 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 make crawl`.
Evidence: `output/runs/20261009T021854Z-86fa5234/`. Two requests, no blocks,
625,476 decoded bytes, one content change, zero new/removed jobs. SQL confirms the
corrected values, changed hash, and preserved first-seen/canonical identity.

`docker compose build crawler && make test` passed **93 tests** and supplied fixture
runs/replays. New cases cover GBP notation, source corroboration, unresolved conflicts
and targeted/unknown maintenance IDs. The captured Wise page parses correctly offline.
Export verification passed after expansion (47 rows/14 requests) and correction
(47 rows/two requests). All ten independent description word streams agree.
Per-row notes: ignored `output/reviews/linkedin-expansion-decisions.json`.

Documented source-field coverage is now **47 listings: 8 Indeed, 26 LinkedIn, 13 Reed**.
LinkedIn has reached the 25-reviewed milestone. These are development reviews, not a
random accuracy sample or proof of a general 95% rate. Next: Reed expansion/review
(12 more needed), then Indeed (17 more needed), retaining the real dedupe-corpus work.

## Reed expansion: fifteen new reviews — 2026-10-09

Command:
`CRAWL_SOURCES=reed CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom" CRAWL_MAX_PAGES=2 CRAWL_MAX_DETAILS=15 CRAWL_MAX_REQUESTS=40 CRAWL_REQUEST_DELAY=2 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Evidence: `output/runs/20261009T022757Z-4f3a1143/`. Four pages returned 100 distinct
IDs; 12 fresh details were skipped and all 15 requested details accepted. 19 requests,
no blocks/failures/rejections, 5,866,364 decoded bytes, zero changes/removals.
The pending queue retained useful candidates from earlier deeper data-engineer pages.

All fifteen new rows were checked against independent source metadata and full
descriptions. **No new source-field extraction defect was found.**

| Source ID | Employer / workplace | Reviewed conclusion |
| --- | --- | --- |
| `reed:57147108` | Connells Group HQ / Milton Keynes | Full-time Data Platform Engineer, £50,000–£65,000/year; source reference `CF00744`. |
| `reed:57168860` | FSP Consulting / Reading | Full-time hybrid Senior Data Engineer; negotiable/competitive salary has no numeric amount. |
| `reed:57265783` | Norton Rose Fulbright / Newcastle | Full-time Data Platform Engineer; competitive salary remains null. Source-supplied abrupt description ending verified in JSON-LD. |
| `reed:57282800` | Breedon Group / Alfreton | Full-time Principal Data Engineer; competitive salary remains null. Specific GB workplace retained despite wider corporate footprint. |
| `reed:57306764` | Sanderson / Cardiff | Contract Data Engineer, £600–£700/day umbrella rate. Three openings remain one source listing. |
| `reed:57312223` | Infoplus Technologies / Bristol | Contract GCP Data Engineer, £450–£500/day; UK-based Bristol/Manchester requirement explicit. No company logo supplied. |
| `reed:57327650` | Liquidline / Ipswich | Full-time Data Engineer, £40,000–£60,000/year from headline/JSON-LD; salary-sacrifice benefits are separate. |
| `reed:57332819` | Vivedia / Sheffield | Full-time hybrid AI Solutions Engineer; negotiable salary stays null. Three Sheffield-office days explicitly stated. |
| `reed:57334111` | SF Partners / St Helens | Full-time Data Engineer, £55,000–£65,000/year; hybrid office requirement explicit. |
| `reed:57354540` | FDM Group / London | Board advertises permanent/full-time Senior AI Engineer, £70,000–£100,000/year; client assignment duration is separate. |
| `reed:57364154` | Acorn Insurance / Liverpool | Full-time Data Engineer, £65,000–£70,000/year; insurance-policy value of £750 million is not salary. |
| `reed:57364627` | Harnham / London | Contract Data Engineer, £400–£420/day; short description is complete as supplied. |
| `reed:57364884` | Norton Rose Fulbright / London | Full-time AI Engineer; competitive salary stays null. Distinct responsibilities from the adjacent data-science listing. |
| `reed:57364885` | Norton Rose Fulbright / London | Full-time Data Scientist & Engineer; competitive salary stays null. Source-supplied ending verified independently. |
| `reed:57379454` | Oliver James / London | Contract Data Engineer; dedicated headline/JSON-LD £650–£750/day takes precedence over £700–£750/day prose. |

### Source inconsistencies and description completeness

- Three Norton Rose Fulbright descriptions have abrupt endings. The same endings
  appear in both the dedicated visible description and the current-page JSON-LD,
  including `reliabili` on the AI role. JSON-LD text lengths are 5048, 5041 and 5100
  characters; the visible-region lengths add exactly the 21-character presentation
  heading/separator. The crawler retains the complete board-served descriptions and
  does not invent missing employer text.
- FDM's board employment metadata explicitly says permanent/full-time, while its
  prose describes a three-month client engagement. Preserve displayed employment
  metadata rather than conflating staff employment with client assignment duration.
- Oliver James supplies a different lower daily rate in prose. The dedicated board
  compensation and JSON-LD agree at 650–750/day and remain authoritative for extraction.
- Recruiter advertiser names/logos are preserved; hidden hiring clients are not guessed.
  Infoplus's absent logo remains null. Nonnumeric salary fields remain null where no
  explicit numeric pay statement is supplied elsewhere in that listing.
- Real negative dedupe examples now include the two Norton Rose London roles with
  the same timestamp/company introduction but different duties, and Connells platform
  versus core-data roles with distinct `CF00744`/`CF00810` references.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T022757Z-4f3a1143 --ids reed:57147108 reed:57168860 reed:57265783 reed:57282800 reed:57306764 reed:57312223 reed:57327650 reed:57332819 reed:57334111 reed:57354540 reed:57364154 reed:57364627 reed:57364884 reed:57364885 reed:57379454`.
All 15 description word streams agree; full descriptions were read for completeness,
eligibility and compensation contradictions. The helper now also writes a readable
`output/reviews/source-metadata.txt` and records structured-description lengths/endings.
Per-row decisions: ignored `output/reviews/reed-expansion-decisions.json`.
Export verification passed for all 62 rows and 19 logged requests.

Documented source-field review now covers **62 live listings: 8 Indeed, 26 LinkedIn,
28 Reed**, with 61 canonical jobs and one linked duplicate. Reed and LinkedIn have
reached 25 reviewed listings. This is development review, not random accuracy grading.
Next: Indeed public first-page partition expansion/review, needing 17 more listings.

## Indeed expansion: twenty new reviews — 2026-10-09

Command:
`CRAWL_SOURCES=indeed CRAWL_QUERIES="software engineer,data engineer" CRAWL_LOCATIONS="United Kingdom,London,Manchester" CRAWL_MAX_PAGES=1 CRAWL_MAX_DETAILS=22 CRAWL_MAX_REQUESTS=180 CRAWL_MAX_SECONDS=600 CRAWL_SAVE_PAGES=1 CRAWL_REFRESH_IDS= CRAWL_FORCE_REFRESH=0 make crawl`.
Evidence: `output/runs/20261009T031307Z-8aadcfaa/`. Six public first-page scopes
returned 82 IDs and skipped five fresh details. Of 22 detail selections, twenty were
accepted and two rejected for missing board-owned identity. No invalid listing was
inserted and no job removed. 78 logged requests, two blocked request records,
33,837,715 decoded bytes, zero content changes/removals. No page-two sign-in attempt.

All twenty new rows were independently reviewed against their bound public panes,
source metadata and full descriptions. **No new source-field extraction defect was
found.** The read-only review helper additionally compares discovery dates to stored
dates: all twenty match with zero conflicting source-date sets. This verifies that
date hints survive scope changes when current selected panes omit publication dates.

| Source ID | Employer / role / workplace | Reviewed conclusion |
| --- | --- | --- |
| `indeed:1f09c85980aadf7c` | JPMorganChase / Lead Java / Glasgow G2 | Chief Technology Office; full-time, salary/logo not supplied. |
| `indeed:24d1d7e6e352b94b` | JPMorganChase / Fullstack Engineer III Java / Glasgow G2 | Platform Engineering; full-time, no listed numeric pay. |
| `indeed:45a469bc422defd3` | JPMorganChase / Senior Lead Java / Glasgow G2 | Finance Technology/Spark responsibilities; full-time, no numeric pay. |
| `indeed:4f29f72d41501e80` | JPMorganChase / Senior Lead Java React AI / Glasgow G2 | AI & ML Data Platforms; full-time, no numeric pay. |
| `indeed:54e89af28ef83fe4` | Openwork / Quality Engineer / Swindon | Up to £55,000/year; minimum/type/logo null where unspecified. |
| `indeed:6ab35cf4f2dd1816` | JPMorganChase / Trading Platforms Lead / Glasgow G2 | Treasury/Chief Investment Office; full-time, no numeric pay. |
| `indeed:754a8d49290f6cec` | Scottish Power / Salesforce AI Lead / Glasgow | Up to £74,000/year; square logo distinct from banner; hours category unspecified. |
| `indeed:757a85d63473258a` | JPMorganChase / Lead Java / Glasgow G2 | Corporate Technology; own full description retained, no numeric pay. |
| `indeed:89fc15da595f38e2` | JPMorganChase / Lead Java AI / Glasgow G2 | Graphite Payments; full-time, no numeric pay. |
| `indeed:d8aa52d3c7900fba` | JPMorganChase / Full Stack React Java Lead / Glasgow G2 | Risk Frameworks; distinct responsibilities, full-time, no numeric pay. |
| `indeed:f329a774c8defe83` | JPMorganChase / Engineering Excellence Executive / Glasgow G2 | Strategic Business Services; source's “Principle” headline retained. |
| `indeed:13abf4d64f8f2cdc` | Capital One UK / Engineering Manager / London | Permanent-only hours category null; no numeric salary; declared logo verified. |
| `indeed:16e55cbef0d97445` | Alfa AI / Lead Software Developer / London | Hybrid, full-time, UK right-to-work explicit; no numeric salary. |
| `indeed:171dee089cc0a51c` | TeamViewer GmbH / Senior Architect / London | Full-time UK workplace despite overseas legal-entity name; no numeric pay. |
| `indeed:1cb9991f8f8dfafd` | Capital One UK / Lead Services Engineer / London | Permanent does not establish full-time hours; type/pay null, source logo retained. |
| `indeed:2c8b21e91b74d8ba` | Capital One UK / Senior Engineer / London | Qualification funding is not salary; type/pay null, source logo retained. |
| `indeed:345023d7eb6fa3ee` | Capital One UK / Staff ML Engineer / London | Distinct ML role; permanent-only type/pay null, source logo retained. |
| `indeed:3e49154a291c8bac` | Muji / Python Developer / London | Full-time, £45,000–£55,000/year, in-person workplace. |
| `indeed:5180a8b50baf518b` | 38 Degrees / Senior Developer / United Kingdom | Explicit UK-eligible remote/home-working role; full-time four-day week, £63,288–£69,430/year. |
| `indeed:95bd9c478263f20d` | Huxley / Full Stack Lead / London | Headline £70,000/year retained over conflicting £90,000–£130,000 prose; permanent-only type null. |

### Additional verified layouts and source differences

- 38 Degrees explicitly requires UK right to work, describes staff based across the
  UK and home working, and labels this role full-time despite a four-day week. Store
  its stated annual pay unchanged; do not invent prorating or classify it part-time.
- Source salary ceilings are one-sided bounds, not fixed salaries. Openwork's minimum
  remains null with maximum 55000; Scottish Power's minimum null with maximum 74000.
- Capital One's four new roles state permanent employment but not working-hours type;
  keeping `work_type` null follows the documented no-guessing policy.
- Huxley has a direct salary/prose discrepancy. The dedicated compensation remains
  70000/year; the hidden investment-banking client is not substituted for the advertiser.
- Scottish Power/Capital One logos match declared square branding URLs. Their wide
  headers are excluded and no logo image is downloaded. Fifteen other new rows have
  null declared logo URLs, supporting stored null values.
- £10 billion investment, £5,000 qualification funding, pension percentages, bonuses
  and equity are not salary. Nonnumeric compensation remains null.
- Discovery salary metadata sometimes contains USD/EUR currency without any salary
  text/amount. Do not infer pay or workplace from that flag; bound GB job metadata
  and public workplace requirements independently establish UK eligibility.
- Similar JPMorgan titles/company boilerplate are not sufficient duplicate evidence:
  team, seniority, technology and responsibilities differ and require real-pair review.
- Two unverified selected IDs never produced bound job identity. They remain failed
  pending work; investigate discovery UI artefacts/retry suppression during efficiency
  tuning rather than treating failures or search absence as job removal.

Review command:
`uv run --locked --offline python -m crawler.accuracy_review --run output/runs/20261009T031307Z-8aadcfaa --ids indeed:1f09c85980aadf7c indeed:24d1d7e6e352b94b indeed:45a469bc422defd3 indeed:4f29f72d41501e80 indeed:54e89af28ef83fe4 indeed:6ab35cf4f2dd1816 indeed:754a8d49290f6cec indeed:757a85d63473258a indeed:89fc15da595f38e2 indeed:d8aa52d3c7900fba indeed:f329a774c8defe83 indeed:13abf4d64f8f2cdc indeed:16e55cbef0d97445 indeed:171dee089cc0a51c indeed:1cb9991f8f8dfafd indeed:2c8b21e91b74d8ba indeed:345023d7eb6fa3ee indeed:3e49154a291c8bac indeed:5180a8b50baf518b indeed:95bd9c478263f20d`.
All twenty description word streams and ID-bound dates agree. Per-row decisions are
in ignored `output/reviews/indeed-expansion-decisions.json`. Export verifier checks
all 82 rows, hashes/counts and 78 logged requests.

Documented source-field coverage is now **82 live listings: 28 Indeed, 26 LinkedIn,
28 Reed**, with **81 canonical jobs** and one linked duplicate. Every board has at
least 25 reviewed listings. This is a development census, not a random/general 95%
accuracy claim. Next: broaden the independently labelled real dedupe corpus and
improve scoped matching evidence, then tune coverage/efficiency and submission materials.
