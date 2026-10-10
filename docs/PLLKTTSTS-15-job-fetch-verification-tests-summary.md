# PLLKTTSTS-15: Verification test summary

Full document: [Verification test plan](PLLKTTSTS-15-job-fetch-verification-tests.md)

These are proposed tests and expected outcomes, not a report of tests already passed.

## Most important checks

- **Regions and priority:** Verify Germany, Netherlands, Switzerland and other
  enabled EU countries before the USA release milestone. Asian searches must make
  zero network requests. Test country aliases, unknown locations, remote-work
  eligibility, and future configuration changes without rewriting historical runs.
- **Matching:** Check title/location translation, radius and posting age, and
  case-insensitive AND matching of description keywords. Missing required details
  stay unresolved rather than becoming confirmed nonmatches.
- **Pagination:** Fetch every accessible page, including pages with no keyword
  matches or only duplicates. Detect source caps, repeated cursors and loops.
  Distinguish a valid terminal empty result from blocking or parsing failure.
- **Failures and storage:** Test bounded retries, timeouts, cancellation, restart,
  and database rollback. Retain earlier successful pages without duplicate jobs.
  Historical jobs must not inflate the current run's accepted count.
- **Verification:** Compare exact expected and actual posting IDs, check persisted
  identities and reconcile record counts. Equal totals alone are insufficient.
  No unresolved or incomplete path may report verified coverage.
- **Live checks:** Use independent captures before/after each search, with the same
  documented criteria. Record two comparison sessions per enabled board/country
  pair; identify changing listings, unsupported filters and access restrictions.

## Examples and expected results

| Scenario | Expected result |
| --- | --- |
| Source pages contain 100, 100 and 45 unique matches. | All 245 IDs are saved. Terminal evidence supports exhausted coverage; an exact independent comparison is also required for verified coverage. |
| Expected IDs are 1-10; fetched IDs are 1-9 plus 11. | ID 10 is missing and ID 11 unexpected; recall and precision are 90%. Equal counts do not pass verification. |
| Berlin results contain six German jobs, two Indian jobs and two unknown work locations. | Accept six, region-exclude two, retain two as unresolved; report partial coverage. |
| A saved search requests India on any board. | Exclude it before fetching: zero network calls and zero accepted jobs. |

## Execution

Use reviewed fixtures, mocked transports, fixed clocks and temporary databases
for automated checks; conduct live comparisons separately in an isolated workspace.
Keep existing regression tests passing. After implementing the proposed tests, run:

```powershell
.\.venv\Scripts\python.exe -m pytest
```
