# SCH-02: Extract the reusable job-fetch backend

**Status:** Pending. **Depends on:** [SCH-01](SCH-01.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

Manual fetching and future scheduled fetching call the same business service
without importing FastAPI routes or depending on HTTP exceptions.

## Work and file ownership

- Create `app/services/job_search_service.py`, `app/services/job_search_errors.py`,
  and an explicit dependency factory. Move orchestration/outcome behavior from
  `app/job_search.py`; leave a thin router translating domain errors to the
  existing HTTP responses. Preserve the replaceable scraper seam used by tests.
- Update `app/job_search_repository.py` to raise domain errors for missing or
  concurrently deleted preferences, preserving SQLAlchemy transactions and
  upsert/link behavior. Define a preference lookup/deletion service seam for
  SCH-06; do not implement schedule-specific deletion policy yet.
- Separate reusable search input/outcome types from transport concerns where
  needed, keeping existing request and response shapes unchanged.
- Allow injection of the board coordination interface agreed in SCH-01. Keep
  the current guard behavior until SCH-05 supplies cross-process coordination.
- Retain board parallelism, keyword/location filtering, result bounds, language
  extraction, warning semantics, and persistence after partial success.
- Dispose owned engines/resources deterministically. Do not refactor unrelated
  application, profile, document, or generation routes in this ticket.

## Acceptance and validation

The service can run with a fake scraper without importing `app.main`; service
and repository code contain no FastAPI exceptions. The existing API still returns
404 for a missing preference, 409 for deletion during fetching, and 502 when all
boards fail. Zero successful matches remain a success; partial results persist.

Run existing job-search, repository, Glassdoor, language, preference, and API
tests affected by the extraction. Add focused transport-independent service tests
in `tests/test_job_search_service.py`, including resource cleanup and injected
failures. Preserve all current test seams or migrate their callers explicitly.

**Handoff:** factory usage, error mapping, injected coordinator contract, and
evidence that manual fetching retains its existing behavior. SCH-05 and SCH-06
can consume this result independently once SCH-03 is also complete.
