# PLLKTTSTS-15: Job-fetch verification test plan

Ticket: [PLLKTTSTS-15](https://kristijanpetkov.atlassian.net/browse/PLLKTTSTS-15)

Companion: [Implementation plan and estimate](PLLKTTSTS-15-job-fetch-completeness-plan.md)

This is the specification for follow-up tests, not a report that those tests have
passed. Existing regression coverage is listed separately below. New coverage
verdicts, run tables, and coverage mode require the proposed implementation first.

## Regional scope and test order

High priority: EU countries, with Germany and the Netherlands as first markets,
plus Switzerland. Medium priority: USA. Asia is excluded. Run European capability
and comparison gates before the USA release milestone; Canada and other unlisted
regions are outside initial scope. See the companion plan for the versioned,
configurable region policy and country-by-country expansion gates.

Initial retrieval adapters are LinkedIn, Indeed, Glassdoor and (for USA only)
ZipRecruiter, where country support is established. Keep Bayt deferred unless an
eligible-country capability review brings it into scope. Use BDJobs/Naukri only
for offline exclusion checks, with no live Asia searches. Test every enabled
board/country pair; a passing Germany test cannot certify all EU countries.

## Test environment and independent oracle

Use pytest, injected board transports, fixed UTC clocks, and temporary SQLite
databases. [tests/conftest.py](../tests/conftest.py) isolates database and log paths.
Never run fixtures or migration checks against `data/cv_builder.db`. Disable live
network access in deterministic tests so unexpected requests fail immediately.
Inject a sleeper/random source to test backoff without real delays.

Proposed fixture directory: `tests/fixtures/job_search_coverage/<board>/`.
Store sanitized raw search responses, detail responses, expected request sequences,
and a manually reviewed reference manifest. Include IDs, original/canonical URLs,
title, description, dates, work-country/location/filter evidence, region-policy
version and priority, expected matching decisions,
continuation, and terminal/error evidence. Expected identities must be written
independently of the production parser and predicate. Test IDs below are stable
report identifiers, not existing pytest function names.

Use two test seams: service fakes for orchestration, and recorded HTTP responses
through the real pinned parser/instrumented adapter for transport, pagination, and
swallowed-error behavior. Merely returning a dataframe from a fake scraper cannot
verify the latter. Parameterize traversal cases across the four initial adapters
and their enabled country pairs using native response formats. Parameterize policy
guards across all seven existing board selections, including deferred/excluded ones.

For every run, assert exact per-board accepted and persisted identity sets; the
record ledger; execution versus coverage verdict; stop reason; effective filters;
and current-run versus historical counts. Do not assert only `fetched` totals.

## Deterministic reference datasets

| Fixture | Data and independent expectation |
| --- | --- |
| Complete traversal | Three source pages contain 100, 100, and 45 unique matching IDs; only the third page has explicit terminal evidence. Expected set is exactly IDs 1-245. |
| Keywords after cap | First 100 distinct descriptions lack `sql`; next page has 16 distinct descriptions with both `python` and `sql`, then an explicit terminal page. Expected accepted IDs are exactly the final 16. |
| Repeated pages | Page 1 has IDs 1-100; page 2 repeats 91-100 and adds 101-190; page 3 adds 191-205 and ends. Raw rows 215, duplicate occurrences 10, accepted unique 205. |
| No local matches | Nonterminal page has 100 confirmed keyword nonmatches; following page has 5 matches and ends. Must fetch both pages. |
| Incomplete details | Ten unique listings: six confirmed matches, two confirmed keyword nonmatches, two inaccessible descriptions. Counts are 6 accepted, 2 excluded, 2 unresolved; coverage partial. |
| Same count, different IDs | Expected IDs 1-10; actual IDs 1-9 and 11. Missing 10, unexpected 11, recall and precision 90%; cannot be verified. |
| Valid empty versus blocked | One correctly structured terminal empty response; one challenge/login response or malformed payload yielding no parsed cards. Only the first is exhausted. |
| Mixed work regions | Ten unique records returned for Berlin: six confirmed German work locations, two confirmed Indian work locations, two unknown/global-remote locations. Accepted 6, region-excluded 2, unresolved 2; raw 10 reconciles; coverage partial. |

## Region policy, priorities, and future expansion

| ID | Setup and action | Required assertions |
| --- | --- | --- |
| REGION-01 | Resolve Germany/DE, Netherlands/Nederlands/NL, Switzerland/CH, France/FR and USA/US through policy configuration. | DE/NL/CH/FR are high priority; US medium. Equivalent aliases have one country identity. Switzerland is eligible independently of EU membership; countries beyond DE/NL remain in the EU scope. |
| REGION-02 | Request India, Bangladesh, China or United Arab Emirates, using each existing board selection in both bounded and coverage modes. | Explicit policy-excluded outcome before transport/detail requests; zero network calls, accepted jobs and run links. No automatic substitution of another country. No excluded-region live fixture capture. |
| REGION-03 | Country is blank, unknown, contradictory, or Canada (outside initial scope). | Explicit unresolved or out-of-scope decision, no worldwide/default-USA network search, and no verified result. Board defaults cannot bypass the regional policy. |
| REGION-04 | Process mixed-work-regions fixture; add a job with Asian employer headquarters but confirmed German workplace, and a globally remote listing without eligible-country evidence. | Fixture has raw 10 = accepted 6 + excluded 2 + unresolved 2. Asian workplace excluded even from an eligible query; headquarters alone do not exclude the German job. Unrestricted remote eligibility remains unresolved. |
| REGION-05 | Queue USA before German, Dutch and Swiss runs in a batch; give high-priority runs identical test durations, then fail one of them. | High priority is scheduled before medium, with bounded concurrency; same-priority tie behavior is deterministic. Failed high-priority work is reported, USA remains scheduled rather than silently discarded, and batch verdict reflects unfinished scopes. |
| REGION-06 | Start a run, change configured priorities/allowlist, then resume it; next run uses the new policy. | Original run retains its policy snapshot and matching decisions; new run uses the new version. Historical Asian jobs remain stored but do not enter new eligible-run counts. |
| REGION-07 | Propose another eligible non-Asian country in config, then an Asian country that also appears in the allowlist. | New eligible country needs explicit priority, capability fixtures and live evidence before verified coverage. Asia exclusion wins conflicting allowlist entries; no network access for the excluded scope. |
| REGION-08 | Mark Glassdoor unsupported for one European country while other board/country pairs pass; select deferred Bayt or Asia-targeted BDJobs/Naukri for an eligible European query. | Unsupported/deferred scopes are visible; no extrapolated verification and no fallback search in an excluded country. No complete EU verdict from representative probes alone. |

## Matching and request translation

| ID | Setup and action | Required assertions |
| --- | --- | --- |
| MATCH-01 | Save Developer, Berlin/Germany, radius 25 km, age 7 days; inspect each board request. Repeat with radius 0, 1, 50 and no age. | Title/location preserved; distances 16, 0, 1, 32 miles respectively; age 168 hours or absent. Snapshot retains original units. Capability evidence identifies ignored/approximate filters. |
| MATCH-02 | Descriptions include mixed-case Python/SQL, Python only, `NoSQL`, empty text, and unavailable detail; keywords are python and sql. Repeat with no keywords. | Preserve current casefolded AND substring behavior, including `sql` matching `NoSQL`. Empty known descriptions are nonmatches with keywords; unavailable required details are unresolved. No keywords means details are not required for matching. |
| MATCH-03 | Test just-inside/outside requested radius and age cutoffs, remote listings, missing location, date-only values, and timezone boundaries with a fixed reference clock. | Board approximation and uncertainty are recorded; no unsupported strict match claim. If a strict predicate is later added, its independent oracle covers each boundary and unresolved data. |
| MATCH-04 | Country is supported, unsupported, blank, unknown, or ISO alias. Select each board in turn. | Indeed/Glassdoor supported-domain rules and other regional restrictions are explicit. Blank/unknown values passing current checks do not imply verified support. Unsupported selected boards remain in the report. |
| MATCH-05 | Start a run, edit preference title/keywords while retrieval is paused, then release it. | Original run criteria and reference time are unchanged; next run uses edited criteria. |

For MATCH-01, inspect only board/country combinations supported for Germany;
ZipRecruiter's European rejection must make no source request. Repeat translation
and capability checks for Amsterdam/NL, Zurich/CH, an additional EU country and
Boston/US. Preserve explicit unsupported outcomes instead of forcing a successful
request on every adapter.

## Traversal, termination, and source evidence

| ID | Setup and action | Required assertions |
| --- | --- | --- |
| PAGE-01 | Fetch complete traversal fixture in coverage mode using native page rules. | Exactly IDs 1-245 persist; raw and accepted counts 245; explicit terminal evidence; no extra source fetch after terminal. Coverage exhausted, or verified only after independent reference equality is attached. |
| PAGE-02 | Fetch keywords-after-cap and no-local-matches fixtures. | All source pages traversed; 16 and 5 accepted respectively. Rejected/accepted counts never determine continuation. |
| PAGE-03 | Fetch repeated-pages fixture; then serve a duplicate-only page with a valid next cursor and later new IDs. | First fixture has raw 215 = accepted 205 + duplicate 10. Duplicate-only nonterminal page does not prematurely end retrieval; later IDs survive. |
| PAGE-04 | Serve empty/short nonterminal page with valid continuation; then a terminal page. Separately serve a repeated cursor or repeating page loop. | Continuation is followed for valid nonterminal data. Loops stop within configured limits with partial coverage and a diagnostic; no infinite fetch. |
| PAGE-05 | Run bounded mode with limits 20, 50, 100, 250, 500, 1000; run proposed coverage mode on fixed sets of 245 and 1500 IDs with different batch sizes. | Bounded mode retains its requested maximum and proposed reporting marks it partial when exhaustion is unproven. Coverage mode can pass the current 1000-job bound; batch changes do not alter expected identities. |
| PAGE-06 | Reach installed LinkedIn/Glassdoor caps; simulate source total larger than accessible set. | Saved jobs remain available; coverage partial with source-cap reason. Request completion does not imply all advertised results fetched. |
| PAGE-07 | For each adapter, use nonzero offsets near native page boundaries; probe actual request sequence and IDs. Include Indeed cursor traversal and Glassdoor range calculations. | No gaps/incorrect slicing, no assumed common page size. Adapter gates fail if the pinned implementation repeats or skips work without reliable evidence. |
| PAGE-08 | Feed terminal empty fixture, challenge page, malformed JSON/HTML, and valid search page with an upstream total but no parsed records. | Only valid terminal evidence permits exhausted empty coverage. Parser/challenge/total contradictions produce failed, partial, or unknown as appropriate. |
| PAGE-09 | Inject HTTP/parsing failures inside real pinned scraper branches that currently catch errors and return JobResponse. | Instrumented report carries failure even if dataframe is empty/nonempty; cannot become exhausted/verified. Uninstrumented interface remains unknown. |
| PAGE-10 | Native source reports totals including duplicate/sponsored records or changes total between pages. | Approximate totals are retained as diagnostics; completion and recall use identity/evidence sets, not count equality. |

## Failures, retries, and recovery

| ID | Setup and action | Required assertions |
| --- | --- | --- |
| FAIL-01 | Page 1 succeeds; page 2 returns 429 with Retry-After then succeeds. Repeat with timeout/503 then success. | Backoff obeys deadline and at most three attempts; page 1 is not counted again; retry attempts are distinct from processed pages; final identity set equals reference. |
| FAIL-02 | After an accepted page, page 2 persistently fails; separately fail before any accepted page. | Attempts bounded; first case partial with earlier jobs saved; second failed if there was no usable retrieval progress. Historical jobs remain. No missing page is silently skipped. |
| FAIL-03 | Mix successful, unsupported, blocked and slow boards; then fail all boards. | Successful board results persist independently. No aggregate verified verdict. Existing all-failed API compatibility is tested; durable run evidence is available even for the error response. |
| FAIL-04 | Hang a transport beyond a small injected deadline; request cancellation mid-run. | Actual transport/worker stops within the configured bound; other boards finish. Counters/checkpoints reconcile and verdict is partial. A timed-out future with a still-running thread fails the test. |
| FAIL-05 | Interrupt after a page commit; resume at saved checkpoint. Also expire a cursor or change source ordering. | Valid resume preserves query, IDs, counters and evidence; no duplicate run links. Invalid checkpoint triggers explicit restart/reconciliation, never a false complete result. |
| FAIL-06 | Fail required description retrieval for two records, then retry successfully in a later attempt. | Initial run reports unresolved IDs and partial coverage. A successful follow-up reports its own evidence; it does not retroactively replace the original run's reference/counters without an audited revision. |

## Identity, database, and reporting

| ID | Setup and action | Required assertions |
| --- | --- | --- |
| STORE-01 | Same source ID with tracking URL variants; two jobs whose URLs differ in an identity query value; same title/company with different IDs; same vacancy on different boards. | Verified aliases collapse only the same board posting; distinct IDs/query values and board postings stay distinct. Original URLs/raw data preserved; applied status works through retained aliases. |
| STORE-02 | Seed 50 historical jobs; fresh run accepts 6 overlapping jobs and 4 new jobs. Repeat unchanged run. | Each run has exactly 10 accepted/persisted identities; historical total 54; inserts versus updates distinguish 4 versus 6 in first run. Repeated fetch changes neither identity nor first-fetch timestamp. |
| STORE-03 | Inject DB failure after the first write of a page; restart persistence. | Entire page write and run links/counters roll back together; earlier committed pages remain. Retry persists exactly once. Persistence failure blocks successful coverage. |
| STORE-04 | Delete preference during fetch; test fresh DB, upgrade from existing schema, and migration rerun. | Explicit conflict/cancellation; no orphan new links or false verified run. Existing applications/jobs/settings/preferences preserved; all new tables have matching model mappings; migration is repeatable. |
| STORE-05 | Return same-count-different-IDs fixture; remove a persisted run link; add unrelated historical job. | Missing/unexpected identities listed with 90% recall/precision in the first case; lost run link is a persistence discrepancy. History cannot fill missing run results. |
| STORE-06 | Reference and actual are both empty; reference missing; reference contains unresolved descriptions. | Exact empty comparison can verify only with valid traversal and criteria evidence; ratios are not applicable for zero denominators. Missing/uncertain reference never produces verified coverage. |
| REPORT-01 | Exercise every coverage verdict, including policy-excluded, and mix boards/countries in one batch. Load UI and browse local pages. | API/UI display run ID, country, priority, policy version, reasons, effective filters, counters and pending scopes. Overall verified only if every requested in-scope board/country pair is verified; explicitly excluded requests cannot be labeled successful. Local pagination and run totals remain distinct. |
| REPORT-02 | Verify two criteria snapshots, restart application, inspect evidence after log rotation. | Stored run/page/reference evidence reproduces the verdict independently of rotated logs. Changed criteria or different dependency versions never reuse a previous verdict implicitly. |

## Existing regression checks

[test_job_search.py](../tests/test_job_search.py) already exercises saved-filter
translation, concurrent default boards, the installed JobSpy schema through a
mocked scraper, keyword/URL filtering, upserts, multiple preferences, applied
status, local pagination, board failures, input validation, and migration 4.
[test_job_search_repository.py](../tests/test_job_search_repository.py) covers
mapped schema, timestamps, transactional rollback, bound text filters, and remote
flags. Keep these passing; extend them only where the new run behavior requires it.

`TestExtendedJobSearchLimit` additionally checks 101- and 1000-job requests with
`posted_within_days=1`: the scraper receives the exact limit and `hours_old=24`,
all returned matching jobs persist, and the rendered UI offers 1000 while retaining
the default of 50. These are offline request/storage checks, not proof that a live
board returns every posting from the last day.

Current focused command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_job_search.py tests/test_job_search_repository.py
```

After adding proposed coverage tests, run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Browser verification for REPORT-01 includes success, limit reached, unsupported
country, Asia exclusion, out-of-scope country, high/medium priority and pending
country runs, blocked empty response, timeout, and partial detail retrieval. Check
warnings and live status text, repeat fetches, stored-list filters, and navigation
after an application restart. This project uses FastAPI and plain browser
JavaScript; these commands do not assume a Node test setup.

## Manual live comparison across websites

Perform this separately from offline tests using an isolated verification
workspace/database and documented captures. Do not attach a live board count to
the user's historical database as proof of the current run.

| Priority and locations | Boards to probe where supported | Comparison cases |
| --- | --- | --- |
| High: Berlin, Germany (`DE`) | LinkedIn, Indeed, Glassdoor | Narrow title, broad title beyond 100, keywords, radius/age evidence, cursors/page alignment, and detail failures. |
| High: Amsterdam, Netherlands (`NL`) | LinkedIn, Indeed, Glassdoor | Same contract; independently verify country aliases/domain mapping, local results, and supported filters. |
| High: Zurich, Switzerland (`CH`) | LinkedIn, Indeed, Glassdoor | Same contract; country-specific support independent of EU membership. |
| High: Paris, France (`FR`), then additional EU countries before enablement | LinkedIn, Indeed, Glassdoor | Representative additional EU probe plus separate evidence for each newly enabled board/country pair. |
| Medium: Boston, USA (`US`) | LinkedIn, Indeed, Glassdoor, ZipRecruiter | Run after European gates; same criteria/evidence checks plus ZipRecruiter pagination. |
| Excluded: Asia | No live boards | REGION-02/04/07 offline checks only; no Dubai, Dhaka, or Bengaluru live searches. |

Locations are proposed probes, not claims of verified live availability. Replace
one only with another location in the same eligible country if city support fails,
and record that outcome. An unsupported country stays an explicit gap; do not
replace it with a different country or an Asian location. For each supported
board/country pair, also test no keywords, two description keywords, no age limit, a recent-age
window, and a city radius where the board supports it. Include a low-volume query
whose accessible results can be fully reviewed and a query exceeding 100 results.

1. Confirm policy eligibility and priority before any search. Record criteria,
   resolved work country, selected boards, language, timezone, login/session state,
   effective native filters, policy/dependency/adapter version, and capture start UTC.
2. Capture the accessible result identities, page/cursor boundaries and required
   detail evidence using manual review or an independent supported export. Mark
   capture caps and inaccessible records explicitly; do not claim a complete
   reference when only the first page was collected.
3. Start a fresh coverage run immediately and retain its page evidence and run ID.
4. Capture reference pages again; record end UTC and compare before/after sets.
5. Independently evaluate matching criteria and compute missing/unexpected sets,
   unresolved identities, recall/precision when defined, and persisted equality
   using the companion plan's definitions.
6. Inspect every difference. Attach evidence for newly posted, withdrawn,
   personalized, unparseable, filtered, capped, or blocked results. Keep original
   counts and differences visible even after classification.
7. Repeat a stable low-volume comparison on a different day. Report per-board/country
   verified/exhausted/partial/unknown/unsupported/excluded/failed outcomes; do not turn a
   blocked comparison into a passing test or infer completeness from cross-board
   overlap.

## Release gates and report format

Deterministic gate: policy tests pass, including zero network access for Asia;
all applicable cases pass for every enabled adapter/country pair; frozen
expected/actual sets are equal, all accepted identities persist, counters
reconcile, and no unresolved/error path reports verified. A fixture can verify a
specific fixed reference without asserting anything about a live board.

Live gate: document two comparison sessions per enabled board/country pair.
Prioritize DE/NL/CH and other enabled EU countries before USA; mark unsupported
pairs and countries awaiting enablement explicitly. Deferred Bayt and excluded
BDJobs/Naukri do not require live tests for this delivery. Exact verified
coverage requires a full, stable independent accessible reference and equivalent
criteria. Otherwise retain the narrower observed verdict. A board without this
evidence may remain usable in bounded mode but must not display full verification.

Record each run with this template:

| Field | Required report content |
| --- | --- |
| Identity | Ticket/test ID, run ID, board, adapter and dependency versions. |
| Scope | Resolved country, priority, policy version, eligibility decision, original/effective criteria, fixed reference time, capture window, source caps. |
| Traversal | Pages/attempts, continuation evidence, terminal/stop reason, elapsed time. |
| Accounting | Raw, accepted unique, duplicate occurrences, exclusions by reason, unresolved, persisted identities, inserted/updated. |
| Comparison | Reference manifest, missing/unexpected IDs, timing classifications, recall/precision or not applicable. |
| Outcome | Execution status, coverage verdict, test pass/fail/blocked, defect and next action. |

Expansion gate: editing the configuration alone does not verify a new country.
Add matching/exclusion fixtures, a board/country capability decision, and two live
comparison sessions before enabling verified coverage for that pair. Policy
changes must leave historical verdicts scoped to their original version.

Re-run deterministic adapter tests after dependency changes and recapture live
evidence when board responses/filter behavior change. A previous run remains
evidence for its recorded query and time window, not a guarantee for future runs.
