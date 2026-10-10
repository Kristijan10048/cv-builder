# PLLKTTSTS-15: Plan to verify job-fetch completeness

Ticket: [How to make sure that all matching jobs are fetched](https://kristijanpetkov.atlassian.net/browse/PLLKTTSTS-15)

Assessment date: 2026-10-10; regional scope updated from the ticket comment edited at 16:44 CEST.

Companion: [Verification test plan](PLLKTTSTS-15-job-fetch-verification-tests.md)

## Deliverables and scope

The ticket comment requests a step-by-step plan, an implementation effort
estimate, and a separate Markdown verification test plan. These documents fulfill
that planning scope. The classes, tables, API fields, tests, and UI behavior below
are proposed follow-up work; they are not implemented by this documentation change.

The objective is to detect and explain missing matching postings on every selected
board. A public board can change its listings during a search, hide results,
personalize rankings, limit accessible pages, or block access. Therefore, a global
claim that every matching job on the internet was fetched cannot be established.
We can prove exact coverage of a fixed reference dataset, verify traversal of a
board's accessible result set, and measure coverage against an independently
captured live reference during a documented time window.

## Regional scope and rollout priority

The updated ticket excludes Asia, gives high priority to the EU (with emphasis on
Germany and the Netherlands) and Switzerland, and medium priority to the USA.
Interpret EU as the full EU scope, with Germany and the Netherlands as the first
validation markets; Switzerland is a separate eligible country. Canada and other
unlisted regions are outside the initial scope.

| Priority | Eligible region | Initial verification locations | Delivery order |
| --- | --- | --- | --- |
| High | Germany (`DE`) | Berlin | First capability, traversal, and reference-comparison milestone. |
| High | Netherlands (`NL`) | Amsterdam | Same milestone and acceptance gates as Germany. |
| High | Switzerland (`CH`) | Zurich | Same milestone; verify independently of EU membership. |
| High | Other EU countries | Country-specific locations; Paris, France, as an additional representative probe | Expand the board/country matrix after the first three countries; retain high priority. |
| Medium | USA (`US`) | Boston | Schedule after high-priority work; include ZipRecruiter where supported. |
| Excluded | Asia | No live searches or reference capture | Offline exclusion tests only; exclusion overrides priority or board defaults. |

Add a versioned `JobSearchRegionPolicy` with explicit country codes, priorities,
Asian-country exclusions, and board/country capability entries. Keep the policy in
configuration instead of scattering country lists through adapters. Resolve saved
country aliases (including Netherlands/Nederlands/NL) to one country code before
scheduling. Blank, unknown, or conflicting countries do not authorize an
unrestricted worldwide search. Record an unresolved scope and require an explicit
eligible country; do not silently substitute the USA or another default.

Check policy eligibility before network access in both bounded and coverage modes,
then inspect returned work-location/remote-eligibility evidence before accepting
postings. Asian work locations are excluded even if a board returns them for an
eligible query. Employer headquarters alone do not determine job geography.
Globally remote or missing/ambiguous location data stays unresolved unless eligible
work countries can be established. Geographic exclusions must be explicit and
tested; query location alone is insufficient proof that every returned job is in
scope. Retain excluded/unresolved counts in run evidence without adding excluded
postings to accepted run results.

Plan initial instrumentation for LinkedIn, Indeed, and Glassdoor in eligible
European countries, subject to country-specific capability checks; add those
boards plus ZipRecruiter for the USA milestone. BDJobs and Naukri are outside this
delivery because their current regional targets are excluded. Defer Bayt unless
the capability audit establishes useful coverage in an eligible country; remove
the earlier Dubai live probe. Keep the seven-board inventory below for context,
without treating deferred boards as required implementation deliverables.

Region priority controls rollout and scheduling, not relevance or completeness
scores. Lower priority must not silently discard requested eligible work. Within
a mixed-country batch, schedule high priority first and retain per-country pending,
partial, or unsupported outcomes; an unfinished USA run is not covered by an EU
success. Verdicts apply to individual board/country/query pairs, not an entire
region based on one representative city.

Future additions require a policy version change, explicit country eligibility
and priority, capability fixtures, and an independent comparison for newly enabled
board/country pairs. Snapshot the expanded policy per run; do not reinterpret
historical runs or remove the Asia exclusion as a side effect of expansion.

## Current implementation and gaps

| Evidence in this repository | Current behavior | Completeness gap |
| --- | --- | --- |
| [JobSearchInput](../app/models.py) and [search form](../templates/available_jobs.html) | Default 50 results per board; API permits 1-1000; UI offers 20, 50, 100, 250, 500, 1000. | Broad searches still stop at the requested limit; the larger bound does not prove exhaustion. |
| [JobSearchAdapter.search_board](../app/job_search_adapter.py) | Calls JobSpy once per board, without an explicit offset or traversal report. | JobSpy may paginate internally, but ApplyKit cannot prove exhaustion. |
| [JobSearchAdapter.build_arguments](../app/job_search_adapter.py) | Sends title, combined city/country, radius rounded up to miles, and age converted to hours. | Passed parameters do not demonstrate that each board applied equivalent filters. |
| [JobSearchAdapter.normalize_records](../app/job_search_adapter.py) | Requires a title and safe HTTP URL; all keywords must occur as case-insensitive description substrings. | Keyword filtering occurs after the result cap; missing descriptions can discard possible matches. Keyword rejections are not counted. |
| [JobSearchOutcome](../app/job_search.py) | A returned dataframe becomes `completed`, including empty data; escaped exceptions become `failed`. | Successful execution is treated as successful retrieval without source coverage evidence. |
| [JobSearchRepository](../app/job_search_repository.py) and [models](../app/database_models.py) | Upsert by `(site, job_url)` and link jobs to preferences; historical results remain stored. | URLs with tracking variants may duplicate jobs. Preference totals mix old and new searches and cannot establish coverage for one run. |
| [Available Jobs UI](../static/available_jobs.js) | Pages stored database rows and displays fetched counts and warnings. | Database pagination does not fetch further source pages. The UI has no coverage verdict. |
| [JobSearchAdapter.validate_country](../app/job_search_adapter.py) | Checks selected boards' country support; no ticket-specific region policy or priority. | Asia exclusion and eligible-region scheduling are proposed follow-up work. |
| [Integration tests](../tests/test_job_search.py) and [repository tests](../tests/test_job_search_repository.py) | Cover arguments, concurrency, persistence, filters, failures, migration, and local pagination with fake scrapes. | They do not compare a complete source universe or prove live retrieval coverage. |

The installed dependency is pinned to `python-jobspy==1.2.0` in
[requirements.txt](../requirements.txt). Inspection of that installed version
shows caught request/parsing errors that return partial or empty `JobResponse`
objects. LinkedIn stops when its start offset reaches 1000; Glassdoor has a
30-page traversal bound and a 900-result clamp. These are observations of the
pinned implementation, not promises about current board limits.

The [upstream JobSpy documentation](https://github.com/speedyapply/JobSpy#parameters-for-scrape_jobs)
describes `results_wanted`, `offset`, and `fetch_description`. A generic offset
parameter does not establish correct continuation on every board. Repeated calls
can repeat earlier work or have page alignment issues, so verify each adapter
before using offsets to extend coverage. Do not edit installed `site-packages`.

## Step-by-step implementation plan

### 1. Freeze the search contract and comparison window

Snapshot the saved preference, resolved country, region-policy version and priority,
selected boards, requested limit, run start/end UTC timestamps, adapter version,
and dependency version. Use a new run identifier
for every attempt; changing a saved preference must not alter an existing run.

Keep the existing matching contract initially: title is a board search expression,
not an exact local title predicate; description keywords are ANDed case-insensitive
substrings. An empty keyword list adds no description requirement. Country, city,
radius, and age remain requested board filters. Record whether each was actually
supported, applied, approximated, or unknown. A strict geographic/date match claim
requires reliable structured location/date data and an independently tested local
predicate; it must not be inferred from a location string alone.

Use a fixed reference time for age checks. Document date-only and timezone
uncertainty. Preserve the current radius conversion, including zero, for baseline
comparison; explicitly probe zero-radius and rounding behavior on each board.
Listings with unavailable required fields are unresolved, rather than confirmed
nonmatches. Do not broaden title synonyms or split locations as if they were
equivalent queries.

Apply the regional policy before constructing a board request. Treat a policy
exclusion separately from unsupported board coverage and from an actual empty
result. Record the scope decision even when no network request is made.

### 2. Audit all seven boards; implement eligible board/country pairs

For each board, record supported countries and filters, native page size,
continuation mechanism, source totals and their meaning, ordering, accessible
caps, terminal-page evidence, detail availability, and error signals. Confirm
behavior with saved responses from the pinned library. Live comparisons are
limited to eligible regions, in priority order; excluded regions use offline probes.

| Board | Current ApplyKit country handling | Planned scope and first probe |
| --- | --- | --- |
| LinkedIn | No country restriction in the adapter. | High-priority Europe, then USA; test offset alignment, caps, blocked HTTP responses, and missing details. |
| Indeed | Requires a resolvable non-worldwide JobSpy country. | High-priority Europe, then USA, where supported; inspect cursor exhaustion and caught page errors. |
| Glassdoor | Requires a supported JobSpy country/domain. | High-priority Europe, then USA, where supported; verify page alignment, range calculation, location resolution, and caps. |
| ZipRecruiter | Rejects a resolved country outside US/Canada. | USA milestone only; verify page/offset alignment and detail failures. Canada is outside ticket scope. |
| Bayt | No country restriction in the adapter. | Deferred pending evidence of eligible-country relevance/support; no Asia live probe or initial instrumentation commitment. |
| BDJobs | Rejects a resolved country other than Bangladesh. | Excluded-region offline policy checks only; no live Bangladesh fetch. |
| Naukri | Rejects a resolved country other than India. | Excluded-region offline policy checks only; no live India fetch. |

For the last three restricted boards, blank/unrecognized country currently passes
the adapter's conditional check; probe this separately and never interpret it as
proven country support. A supported-country matrix needs positive and negative
fixtures, not just acceptance by the current validator.

Publish the matrix by country and board, including unsupported combinations.
Start with DE, NL, CH and an additional EU probe, then US; audit remaining eligible
EU country mappings before enabling them. A board failure in Switzerland cannot
be hidden by success in Germany. Defer live tests for countries not yet enabled
and label their coverage pending instead of extrapolating regional verification.

**Gate:** Do not enable verified coverage for a board until continuation and error
evidence are observable. The dataframe-only interface is insufficient. Prefer an
upstream structured report; otherwise use a versioned, tested project adapter or
maintained fork that exposes page and detail outcomes. Log-message parsing alone
is not a trustworthy completion signal. Keep uninstrumented boards `unknown`.

### 3. Add durable run and board evidence

Propose these responsibilities, keeping scraping, orchestration, and persistence
separate from the existing service:

- `JobBoardCapability`: versioned country/filter/continuation capabilities.
- `JobSearchRegionPolicy`: configurable country eligibility, exclusions, priority,
  and versioned expansion rules.
- `JobBoardPageOutcome`: raw records, next cursor/offset, terminal evidence,
  source total semantics, page identity, and explicit transport/parser failures.
- `JobSearchCoverageService`: traversal, budgets, retries, and coverage decisions.
- `JobSearchVerificationService`: independent reference comparison and reporting.

Add mapped classes and a new versioned migration for `job_search_runs`
(`JobSearchRunModel`), `job_search_board_runs` (`JobSearchBoardRunModel`), and
`job_search_run_results` (`JobSearchRunResultModel`). The run stores the immutable
criteria, resolved country, policy version and priority; each board record stores
execution, coverage, counters,
stop reason, and a page-evidence manifest; run-result rows link the exact accepted
jobs for that run. Reference manifests retain expected identities, unresolved
records, capture window, and matching decisions. Page evidence must distinguish
every retry attempt from the one successfully processed page.

Follow the [migration workflow](../app/db_migrations/README.md); include a model
for every new table and build data queries through SQLAlchemy query classes.
Preserve existing jobs, applications, preference links, and applied flags. Retain
run snapshots if a preference is deleted. Configure evidence retention explicitly
so a later report cannot silently lose the basis for its verdict.

### 4. Traverse source results and account for every record

Use separate options for page batch size and whole-run budgets. Keep existing
`results_wanted` as the maximum requested postings in the existing bounded mode;
add an explicit coverage mode that traverses accessible results instead of
silently changing the limit's meaning. Local `page_size` remains a display option.

For each selected board:

1. Apply regional eligibility before networking, then validate country and filter
   capabilities; save policy exclusions and unsupported/approximate criteria.
2. Fetch a page using that board's verified cursor or page rules.
3. Save raw-page counts, source IDs, continuation, terminal evidence, and errors
   before local filtering. Advance by source continuation, never accepted count.
4. Obtain required details, normalize records, classify exclusions/unknowns, and
   upsert accepted jobs with their run associations.
5. Continue even if a page produces zero keyword matches or only duplicate jobs
   when the source reports a next page. A short dataframe alone is not exhaustion.
6. Stop on trustworthy source exhaustion, a known source cap, user budget,
   deadline, repeated continuation/page loop, persistent error, or cancellation.
   Save the stop reason and available postings for every path.

Use a board-scoped stable source ID where available; otherwise use a tested
board-specific canonical URL. Strip only verified tracking parameters, retaining
identity-bearing query values such as Indeed's job key. Preserve the original URL
and source data. Map URL aliases to the existing stored identity without breaking
application URL matching; ambiguous collisions stay unresolved. Do not merge
postings across boards by title/company. Cross-board vacancy clustering can be a
later feature and must not hide a missing posting on one board.

Maintain a mutually exclusive record ledger:

`raw rows = accepted unique + duplicate occurrences + confirmed exclusions + unresolved rows`

Partition exclusions into region, keyword, invalid record, and any separately implemented
strict filters. A detail failure needed for keyword evaluation is unresolved.
Require `accepted unique = successfully persisted run-result identities` before
reporting success. Old preference-linked jobs do not contribute to this equality.

### 5. Bound retries and preserve partial progress

Proposed initial defaults: batches of 100 where supported, at most three attempts
per transient request, a 15-minute board deadline, 100 source pages, and 10,000
raw rows per board. Put configurable constants under descriptive `C_` names;
review these defaults after measurement. Smaller native caps take precedence.

Retry timeouts, rate limits, and retryable server errors with bounded exponential
backoff/jitter; respect `Retry-After` within the deadline. Do not retry unsupported
countries, authentication challenges, or stable parser failures indefinitely.
Persist accepted pages and checkpoints atomically so later failures retain earlier
results without duplicate run links. A checkpoint includes cursor, query snapshot,
seen identities, and counters; restart if the source cursor is expired or unstable.

Set transport timeouts as well as orchestration deadlines. Timing out a future
does not stop a running scraper thread; use cooperative cancellation or an
isolated worker that can be stopped. One blocked board must not prevent others
from finishing. Interrupted runs must recover as partial, never complete.

### 6. Report execution and coverage separately

Retain existing API fields where feasible and add `run_id`, per-board coverage,
stop reasons, requested/effective filters, and raw/accepted/duplicate/excluded/
unresolved/persisted counts. An execution status such as `completed` only states
that execution ended. Coverage uses the following proposed vocabulary:

| Coverage | Required evidence |
| --- | --- |
| `verified` | Independent fixed reference set matches exactly, traversal/persistence passed, required criteria are supported, and no unresolved relevant records remain. Include reference scope and time window. |
| `exhausted` | Instrumented traversal reached a valid terminal state with no unresolved relevant records or traversal errors; independent reference equality is not established. |
| `partial` | Result budget, source cap, deadline, page loop, unresolved details/records, persistence failure, or interrupted traversal prevents coverage. |
| `unknown` | Missing instrumentation, unavailable reference/effective filter evidence, or indistinguishable empty/error output prevents assessment. |
| `unsupported` | A selected board cannot support the requested scope. |
| `excluded` | Regional policy disallows the requested country; no source request was made. Distinct from a zero-result or unsupported-board response. |
| `failed` | No usable retrieval progress because requests or setup failed. |

Do not offer an overall verified verdict unless every selected board is verified
under the same contract. An explicitly deselected board is outside scope; an
unsupported or policy-excluded selected scope remains visible and prevents full
verification of the requested batch. Report deliberately out-of-scope regions
separately; excluded Asia is not part of eligible-region recall denominators.
Show per-board reasons and next actions in Available Jobs, for example
"100 saved; source limit reached; coverage partial". Keep historical list totals
separate from current-run counts. A legitimate exhausted empty search must be
distinguishable from a blocked search that returns no rows.

Also display requested country, priority, policy version, scope decisions and any
pending country runs. Region filtering of existing history must be explicit; do
not delete historical Asian jobs or treat them as fresh eligible results.

### 7. Compare identities with an independent reference

Build offline reference manifests independently of the production parser using
reviewed saved page/detail fixtures. For live verification, manually capture all
accessible result pages or use a separate board-supported export/reference path;
do not use a second identical JobSpy call as the only oracle. Record the exact
search URL, visible filters, UTC capture interval, language, timezone, login state,
ordering, region-policy version, work-country eligibility, page boundary, and any
access cap. Capture board totals as supporting
evidence, not the ground-truth identity set.

Apply the documented contract independently to captured details. For each board,
let `expected` be confirmed matching reference IDs and `actual` be accepted IDs
from that run, using the same reviewed identity rules:

- `missing = expected - actual`; investigate page, detail, filter, identity, or
  persistence loss for each ID.
- `unexpected = actual - expected`; inspect relevance, capture timing, or
  reference gaps for each ID.
- `recall = |expected intersection actual| / |expected|` for a nonempty expected
  set; otherwise report recall as not applicable and compare exact empty sets.
- Also report confirmed-match precision with the corresponding actual denominator,
  unresolved identities, duplicate rate, and persistence discrepancies.

For frozen fixtures require no missing/unexpected IDs, no unresolved rows, and
100% recall/precision when defined. Equal counts alone can hide swapped postings.
For live data, bracket the fetch with before/after reference captures and classify
new/deleted listings with evidence. Preserve the original differences; do not
silently remove missing IDs to improve recall. If the reference is incomplete,
personalized, capped, or changing without an explainable comparison, report
`unknown` or `partial` and observed recall only. Agreement between different boards
does not prove any individual board complete.

### 8. Validate and enable boards incrementally

Execute the [verification test plan](PLLKTTSTS-15-job-fetch-verification-tests.md).
Start with deterministic fixtures and migration/repository checks, then manual
live comparisons for enabled board/country pairs: Germany, Netherlands,
Switzerland and other EU countries first, then USA. Test excluded Asia offline
without live network calls. Enable verified traversal one board/country pair at
a time. Keep bounded mode available and disclose coverage limitations
for adapters that have not passed their gates. Re-run adapter contract tests after
dependency upgrades and recapture a small live reference when behavior changes.

## Effort estimate for follow-up implementation

Estimate: one developer familiar with this code, eight productive hours per day,
four initial boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter), a configurable
regional policy, no paid-source integration, and access to representative saved/live
responses for the initial European and USA probes. The seven-board audit remains,
but Bayt/BDJobs/Naukri instrumentation is excluded from this estimate. Ranges
include coding, review, and the tests in each phase;
the final phase adds integration and live evaluation, not duplicate unit-test work.

| Sequential work package | Developer days | Exit evidence |
| --- | ---: | --- |
| Search contract, regional policy, pinned-library probes, capability matrix, reference format | 2-3 | Seven-board inventory classified; eligible country/board scope and policy tests defined. |
| Run models, migration, SQLAlchemy repository, counters and atomic progress | 2-3 | Fresh/upgrade schema checks and reconciliation pass. |
| Instrumented adapters for the four initial boards, continuation and detail/error reports | 3-5 | Recorded-response traversal tests pass for enabled board/country pairs. |
| Coverage orchestration, budgets, retries, recovery and identity aliases | 3-5 | Failure, cap, duplicate and resume scenarios pass. |
| API compatibility and Available Jobs coverage display | 1-2 | Run evidence is visible without mixing history. |
| Independent comparison report, full regression and live evaluation | 3-4 | High-priority DE/NL/CH/additional EU probes first; USA go/no-go afterward. |
| **Base total** | **14-22 days (112-176 hours)** | Evidence-backed coverage for enabled board/country pairs. |
| Explicit contingency for board changes or adapter/fork repairs | **3-5 days (24-40 hours)** | Used only when probes expose additional work. |
| **Planning range with contingency** | **17-27 days (136-216 hours)** | About 4-6 working weeks for one developer. |

A first milestone of **4-6 days (32-48 hours)** covers the first two work packages:
capability findings and durable run evidence. It is included in the total and does
not yet implement complete traversal. Re-estimate after the first package if
instrumentation requires a larger fork. Access restrictions can prevent live
verification regardless of engineering effort; record blocked board outcomes and
elapsed waiting time separately. Paid APIs, new boards, strict geocoding, cross-board
vacancy merging, and continuous monitoring infrastructure are outside this estimate.

The updated range replaces the earlier seven-board estimate of 18-29 days.
Removing three instrumentation targets saves adapter work; country-specific checks
and exclusion/priority tests remain necessary. The range is for the initial
European probes and USA milestone, not exhaustive live certification of every EU
country. Plan an additional **0.5-1 day (4-8 hours) per added country** using the
same working adapters, for capability fixtures and two comparison sessions; a new
adapter or board-specific repair requires a separate estimate. This extension
allowance is outside the base total. Verify high-priority country pairs before
starting the USA release milestone, and report unsupported pairs explicitly.

## Acceptance checklist for this ticket

- [x] Repository-specific completeness gaps and all seven boards documented.
- [x] Asia exclusion, high-priority EU/Germany/Netherlands/Switzerland, medium-priority
  USA, and configurable future expansion incorporated.
- [x] Step-by-step follow-up plan with measurable coverage definitions provided.
- [x] Implementation effort, assumptions, milestones, and uncertainty provided.
- [x] Separate verification test document linked, with fixtures and live checks.
- [x] Proposed behavior distinguished from existing implementation.
