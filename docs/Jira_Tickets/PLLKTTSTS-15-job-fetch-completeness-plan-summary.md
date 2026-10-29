# PLLKTTSTS-15: Completeness plan summary

Full document: [Implementation plan and estimate](PLLKTTSTS-15-job-fetch-completeness-plan.md)

This summarizes proposed follow-up work; coverage verification is not implemented yet.

## Most important points

- **Goal:** Find missing matching postings and explain retrieval limits for each
  board/country/search. A completed request alone does not prove full coverage.
- **Regions:** High priority is the EU, especially Germany and the Netherlands,
  plus Switzerland. USA is medium priority. Exclude Asia before network access
  and reject returned Asian work locations. Unknown work-location eligibility
  remains unresolved. Keep eligibility and priorities configurable for expansion.
- **Boards:** Start with LinkedIn, Indeed and Glassdoor in supported European
  countries; add ZipRecruiter for USA. Defer Bayt; BDJobs and Naukri are outside
  this delivery's retrieval scope.
- **Current gap:** Searches now request up to 1,000 results per board and apply
  description keywords afterward. Missing later pages or internally caught scraper
  errors can leave matching jobs unfetched.
- **Implementation:** Record each run's criteria and policy version; traverse
  source pages using verified continuation rules; deduplicate by posting identity;
  preserve partial progress; count accepted, duplicate, excluded and unresolved
  records. Keep current-run counts separate from historical database totals.
- **Evidence:** Compare actual posting IDs with an independent reference set.
  Use `verified` only with exact reference agreement and complete supporting
  evidence; `exhausted` means accessible traversal ended; `partial` means coverage
  is limited. Show unknown, unsupported, excluded and failed outcomes explicitly.

## Example

Search for Developer jobs in Berlin with description keywords `python` and `sql`.
Both keywords must match, ignoring case. Suppose the first 100 postings lack
`sql`, but the next page has 16 matches. Stopping after the first batch misses
those 16 jobs. Coverage mode must continue by source-page evidence even when no
local matches are found, save the 16 jobs, and compare their IDs with the reference.

If a later page is blocked, report partial coverage and retain saved jobs.

## Effort

Initial implementation: **14-22 developer days**, or **17-27 days including
contingency**, for one developer. This covers initial European probes and USA,
not live certification of every EU country. Allow **0.5-1 additional day per new
country** using existing working adapters; new adapters need a separate estimate.
