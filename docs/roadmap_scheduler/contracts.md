# Scheduler contract v1 — SCH-01

The executable source of truth is `app/scheduler/contracts.py`, with limits in
`constants.py`, startup settings in `configuration.py`, and transport-independent
errors in `errors.py`. This ticket adds no database tables, routes, worker entry
point, or scraper calls. Importing any of these modules does not initialize them.
The JSON examples use a frozen clock of **2030-01-01T00:00:00Z**; consumers must
inject that instant when validating examples rather than depend on wall time.

## Wire contract

All scheduler-owned objects reject extra properties. Integer fields reject bools,
numeric strings and floats. Timestamps accept aware datetimes internally and
offset-bearing ISO 8601 strings externally, normalize to UTC and serialize with
one `Z`. Naive dates and numeric epochs are invalid. Names are trimmed, 1–120
characters. IDs and revisions are positive integers. New schedules are enabled,
revision 1; the nondeleted schedule limit is 100.

Definitions contain `name`, `task_type: "fetch_jobs"`, `payload_version: 1`,
`payload` and `trigger`. Payload reuses `JobSearchInput` defaults and bounds:
positive `preference_id`, distinct supported `sites`, `results_wanted` 1–1000,
default 50. Defaults for sites match the manual route. Unlike manual fetching,
duplicate sites are rejected, not silently collapsed. No callable, module, script,
SQL, or arbitrary task type can be supplied. Production registry keys are the
allowlisted `(task_type, payload_version)` pair; fake handlers replace that pair
through dependency injection and never add a public `fake` task type.

Location depends on the current saved preference, so syntax validation alone
cannot check it. SCH-02/SCH-06 must reuse the offline country resolution and
`JobSearchAdapter.validate_country` rules on create/replace; SCH-05 rechecks at
execution. Preserve the current per-board partial-success behavior when a later
preference edit makes only some boards invalid. Indeed/Glassdoor require a supported
country; Glassdoor additionally requires a domain; ZipRecruiter allows US/Canada,
Naukri India, BDJobs Bangladesh (including existing unspecified-country behavior).
Do not duplicate the JobSpy country catalog inside scheduler contracts.

Triggers are discriminated by `kind`:

- `interval`: `seconds` 300–31,536,000 and `starts_at`.
- `once`: `run_at`.

Creation requires a future anchor. `CreateScheduleRequest` accepts a validation
context `{"now": aware_datetime}`; otherwise it uses current UTC. Repositories
recheck under the transaction with the injected clock. Replacement checks the
current revision and calls `validate_against(current, now)` inside its transaction:
an unchanged normalized trigger can have a past anchor; a changed trigger must
have a future anchor. Name/payload-only changes preserve the due time. PUT does
not change enabled state. Trigger edits while paused store the new definition but
leave eligibility null. Clients send all editable fields for PUT.

`ScheduleRecord` includes definition fields, `id`, `revision`, `enabled`, `deleted`,
`next_run_at`, creation/update times, `active_run_id`, and `latest_run`.
`RunRecord` includes summary fields plus schedule/revision, manual key and expiry,
owner token, `claim_snapshot`, and nullable `effective_preference`.
`claim_snapshot` is a storage-owned deep copy of the definition at claim time;
`effective_preference` is a separate deep copy of the saved-search criteria read
immediately before scraping. Never rewrite one snapshot with the other. Manual
requests snapshot at request acceptance, timed requests at claim. Repository
outputs must be detached copies: callers cannot mutate persisted snapshots.

`TaskResult` has `state`, distinct persisted posting count `fetched`, per-board
`boards`, `warnings`, and nullable safe `error`. Board statuses are `completed`,
`partial`, `failed`, `busy`, `cooldown`, each with `count` and `warnings`.
At least one successful board plus any failure/busy/cooldown/partial warning yields
`partial`; all failed/unavailable boards yield `failed`; complete boards without
warnings yield `succeeded`. Zero matches can succeed. Failed results require an
error; other results have no error. Full descriptions/postings are not run results.

## API routes and examples

`contract_examples.json` supplies named models, per-route cases, lifecycle runs,
and fake-handler fixtures. Each case identifies its request/response model and
status; null model/body means no body (including DELETE 204). Model JSON schemas
are available through `model_json_schema()`. The tests validate every example and
require route/scenario coverage. Examples are offline API/UI fixtures, not evidence
that these endpoints already exist.

| Method/path | Request | Success response |
| --- | --- | --- |
| GET `/api/task-schedules` | `PaginationRequest` query | 200 `Page[ScheduleRecord]` |
| POST `/api/task-schedules` | `CreateScheduleRequest` body | 201 `ScheduleRecord` |
| GET `/api/task-schedules/{id}` | positive path ID | 200 `ScheduleRecord` |
| PUT `/api/task-schedules/{id}` | `ReplaceScheduleRequest` body | 200 `ScheduleRecord` |
| POST `/api/task-schedules/{id}/pause` | `RevisionRequest` body | 200 `ScheduleRecord` |
| POST `/api/task-schedules/{id}/resume` | `RevisionRequest` body | 200 `ScheduleRecord` |
| DELETE `/api/task-schedules/{id}` | `RevisionRequest` query | 204, no body |
| POST `/api/task-schedules/{id}/run-now` | `RunNowRequest` body | 202 `RunNowResponse` |
| GET `/api/task-schedules/{id}/runs` | `PaginationRequest` query | 200 `Page[RunRecord]` |
| GET `/api/scheduler/status` | none | 200 `WorkerStatus` |

Pagination: `items,total,page,page_size,total_pages`; page >=1, size 1–100,
default 20; empty collections have 0 total pages. Out-of-range pages are empty,
not 404. Schedule order is id ascending; history is queued_at/id descending.
An absent schedule is 404; retained tombstone history remains readable. Normal
list/get excludes tombstones. No-route-body requests still validate path/query.
Read routes have no revision conflict case; no-body routes have no JSON validation
case. Unsupported query parameters are 422. Invalid path IDs are 422.

Every error uses `{"error":{"code":...,"message":...,"path":[],
"current_revision":null,"schedule_ids":[]}}`. `path` contains only safe field
names/indexes (no rejected input or traces). On validation return the first safe
issue, not Pydantic's raw input-containing exception. Storage errors do not expose
database paths. Error codes and HTTP mapping:

| Code | HTTP | Meaning |
| --- | --- | --- |
| `schedule_not_found` | 404 | Absent/deleted definition or absent retained run |
| `revision_conflict` | 409 | Stale revision; include `current_revision` |
| `active_run_conflict` | 409 | Another queued/running request exists |
| `idempotency_conflict` | 409 | Same key with a different expected revision |
| `schedule_limit_reached` | 409 | 100 live schedules already exist |
| `preference_in_use` | 409 | Preference deletion blocked; include `schedule_ids` |
| `preference_not_found` | 422 | Create/replace references a missing preference |
| `validation_error` | 422 | Syntax, limits, location, or future-anchor failure |
| `unsupported_task` | 422 | Unknown registry pair; no dynamic import |
| `storage_unavailable` | 503 | Bounded transient database contention |

Run-only codes: `task_failed`, `submission_failed`, `claim_invalidated`,
`request_expired`, `worker_interrupted`, plus `unsupported_task` for corrupt or
disabled persisted registry entries. They are history details, not management HTTP
errors. Translate unknown internal exceptions to a generic safe failure message.

## Revisions, manual dedupe, and deletion

Each successful replace/pause/resume/delete increments revision exactly once,
including an already-paused pause or already-enabled resume. The latter preserves
the existing due time. Every state-changing request supplies the current revision.
Pause clears `next_run_at`. Resume a paused interval at the first anchor occurrence
strictly after now; an overdue once must first receive a future trigger through PUT.

Run now supplies `{revision,idempotency_key}`. Keys are case-sensitive, scoped to
schedule ID, 1–128 ASCII letters/digits/`._:-`, starting with a letter/digit.
Within a transaction: require a live schedule; look up retained key before checking
current revision or active work; identical original revision returns the existing
run with `deduplicated:true` even after later edits/completion. Different revision
with that key gives 409. A new key requires current revision and no active run.
Accepted work snapshots the definition, expires at queued_at +300 seconds, remains
unowned until claimed, and returns 202 even with a stopped/stale worker. Include
the offline warning and actual worker status; never describe acceptance as started.
Manual work can run against a paused current revision without resuming it. Its
completion never changes recurrence or consumes a once occurrence. Pruning removes
its key, so default dedupe is 90 days after terminal completion (longer if cleanup
lags); retention changes this window. Tombstoned schedules reject new or repeated
run-now requests, while retained history remains accessible.

Deletion is a tombstone, clears the schedule preference FK, and prevents new
claims. Payload/history snapshots still keep the original preference ID. Already
running work can finish. DELETE returns 204 (no warning body); the UI confirmation
must always say running work may finish. Pause/replace responses expose active_run_id.
Preference deletion must check live references in the SAME transaction as deletion;
`referencing_schedule_ids()` alone is not a race-safe authorization to delete.
SCH-06 must integrate that guard through SCH-02's repository seam. This is an
integration requirement, not permission to change the existing repository here.

## Dispatch and atomic storage semantics

SCH-04 owns trigger calculation. For anchor A, interval I and now N >= A, latest
occurrence L = A + floor((N-A)/I)*I. Count due occurrences from persisted next due D:
`count = (L-D)/I + 1`. Next due is L+I, never completion+I. Coalesce to L; when
N-L <=300 seconds queue it with `skipped_count=count-1`. Otherwise record one
`missed` summary with `skipped_count=count` and advance. A once occurrence uses
the same inclusive lateness boundary, and a missed once disables its schedule.
An active schedule produces `skipped_overlap` with `skipped_count=count` and
advances; overlap wins over lateness. An overlapped once is consumed and disabled.
This avoids an immediately repeated overlap record for the same occurrence.

No free capacity: leave runnable timed records unclaimed, re-evaluate lateness
next tick. Terminal overlap/missed summaries and manual expiry do not need a slot.
Alternate timed/manual selections across ticks; each source is oldest-first.
Reserve capacity before claiming runnable work. `TimedClaim` carries expected
revision and due time plus calculated outcome/next time. `claim_timed` rechecks
all of these, enabled/deleted status and active work under one transaction; losing
a race returns None for recalculation. Snapshot, insert and advance commit together.
At most one active run per schedule is enforced by a database constraint; terminal
summaries do not count as active. Timed uniqueness is `(schedule_id,revision,
scheduled_for)` with scheduled_for=L, manual uniqueness is `(schedule_id,key)`.

`claim_manual` assigns only an unowned unexpired queued row, without touching
recurrence; invalid requests are cancelled/missed rather than invoked. `start_run`
is the final atomic gate, checking ownership, deletion, revision and for timed
runs enabled state. Manual runs may start on the current paused revision. Expiry
at `now >= expires_at` is missed. Return the resulting record and invoke the
handler ONLY if running. An invalid claim returns cancelled with claim_invalidated.
After this boundary later edits do not cancel running work. The handler reads the
current saved preference and calls `record_effective_preference` before network
work, then preserves existing preference-existence checks at persistence.

Allowed transitions: queued -> running/cancelled/missed/interrupted;
running -> succeeded/partial/failed/interrupted. Missed/skipped_overlap may also
be inserted directly as terminal dispatch summaries. All terminal records have
finished_at. Only running has started_at (retained after finishing). Completion
requires the same owner and running state, and atomically stores the result. It
disables a once schedule only for its timed occurrence and still-current revision;
an edit that replaces the trigger during execution must survive completion.
Terminal states are immutable; a repeated identical completion is idempotent,
incompatible/invalid owner transitions are active_run_conflict.

If executor submission fails while queued, `cancel_submission` records cancelled /
submission_failed, and releases capacity; if work already started, its handler/future
must record failure instead. No implicit retries or due-time rollback. Reservations
must be released on every claim failure; submit transfers the slot to the future.
SCH-04's submitted wrapper calls start_run immediately before handler invocation.
Its future returns TaskResult after execution, or None if the final gate already
persisted cancelled/missed. Completion callbacks do not complete a None result.
Future exceptions become safe failed TaskResult via complete if already running;
if still queued, use cancel_submission. Executor shutdown drains all tasks; thread
timeouts cannot terminate blocked network calls.

After the singleton lock is acquired, `recover` atomically registers the new owner
and marks unfinished OWNED old-worker runs interrupted, without replay or rewind.
Unowned durable manual queue entries survive restart and may execute until expiry.
Heartbeat updates require current owner and a successful dispatch pass; do not
refresh health from an independent timer after dispatch has stopped. Fresh means
heartbeat age <=30 seconds with no stopped_at; absent/stopped rows mean stopped;
other rows mean stale. Counts include all active runs. Stable worker slot is one
row per database; ownership tokens fence writes but do not replace the OS lock.
Retention deletes terminal rows with finished_at strictly before cutoff, oldest
finished_at/id first, at most 100 per default batch; never delete active rows.
Keep tombstones while referenced history exists (keeping them longer is allowed).

## Configuration and dependencies

Load `SchedulerConfiguration.from_environment()` explicitly at startup. Relative
paths use the CV Builder root derived from this module, not cwd. Loading settings
creates no directories, database, log, threads, or locks. Startup owners create
directories and report permissions/open failures before becoming healthy.

| Variable | Default | Validation |
| --- | --- | --- |
| APPLYKIT_DATABASE_PATH | data/cv_builder.db | local file path |
| APPLYKIT_LOCK_DIR | data/locks | local directory path |
| APPLYKIT_SCHEDULER_LOG_DIR | logs | local directory path |
| APPLYKIT_SCHEDULER_MAX_WORKERS | 2 | decimal integer 1–32 |
| APPLYKIT_SCHEDULER_POLL_SECONDS | 5 | decimal integer 1–10 |
| APPLYKIT_SCHEDULER_RETENTION_DAYS | 90 | decimal integer 1–3650 |

Worker freshness=30s, SQLite busy wait=5s, migration lock wait=30s, history
batch=100, manual expiry/lateness=300s. Log file scheduler.log, INFO,
5 MiB rotation and 3 backups; no new log-level environment variable. Booleans,
fractions, signs, blank values and invalid ranges are rejected as settings.

Database identity is SHA-256 of resolved, platform normcase absolute path encoded
UTF-8. Lock files: `<identity>.worker.lock`, `.migration.lock`, and
`.board-<supported-site>.lock` in the configured shared lock directory. Both
processes MUST receive identical database and lock settings. Different lock roots
cannot coordinate. Local disk only; UNC/network shares, hard-link/alternate drive
aliases and multiple hosts are unsupported. Never unlink/recreate a lock file
while processes may hold it. Worker/per-board locks use portalocker EXCLUSIVE |
NON_BLOCKING with timeout=0; migration lock uses bounded retry. Keep handles open
until protected work ends; process death releases the OS lock. Persist Glassdoor
cooldown in the database while holding the shared board lock; a busy board returns
a warning immediately, never occupies worker capacity waiting on another search.

Application dependency pins: **APScheduler==3.11.3**, **portalocker==3.2.0**.
No Jira requirements changed. Tested platform: Windows x64, CPython **3.14.7**;
this is the supported/tested SCH-01 baseline, not a claim of a full Python matrix.
APScheduler metadata requires Python >=3.8; portalocker >=3.9. Existing app syntax
requires >=3.10. Observed environment: Pydantic 2.13.4, FastAPI 0.116.1,
SQLAlchemy 2.0.44, tzlocal 5.4.4, pywin32 312 (portalocker's Windows dependency).
The latter are observed transitive versions, not new top-level pins.

References checked for the selected versions:
[APScheduler 3.x guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html),
[3.11.3 metadata](https://pypi.org/pypi/APScheduler/3.11.3/json),
[portalocker 3.2.0 README](https://github.com/wolph/portalocker/blob/v3.2.0/README.rst),
[3.2.0 Windows implementation](https://github.com/wolph/portalocker/blob/v3.2.0/portalocker/portalocker.py),
[3.2.0 metadata](https://pypi.org/pypi/portalocker/3.2.0/json).
The current portalocker latest docs describe 4.x; they are not the selected API.
Use BlockingScheduler, memory store, one dispatcher with coalesce=True and
max_instances=1; business work has its own bounded executor. Compatibility tests
configure this object without starting any scheduler.

## Ownership and downstream handoff

No roadmap-default deviations. Added precision: integer config bounds, key format,
idempotency revision fingerprint, snapshot shapes, terminal-summary precedence,
unowned manual recovery, and unchanged-trigger edit behavior. No migration version
allocated. Interfaces remain owned by SCH-01; propose amendments here for integration.

- SCH-02: extract transport-independent fetching; expose country/preference validation
  and safe failure seams without changing the existing manual HTTP response.
- SCH-03: implement BaseScheduleRepository, map each table, wire shared configuration
  into app/database.py and serialize migrations. Enforce transaction-level live
  preference references, active-run exclusion and detached snapshots.
- SCH-04: implement calculations/reservations/final start gate and memory dispatcher.
- SCH-05: implement allowlisted FetchJobsTaskHandler and shared board coordination.
- SCH-06: wire the route/model/error table, context clock, query validation and
  preference deletion guard; never execute handlers during API requests.
- SCH-07/SCH-08: consume populated/empty/offline/conflict fixtures, show run-now as
  queued, display all lifecycle states and warnings; no second Z suffix.

Validation evidence and checkout limitations are recorded in the SCH-01 ticket.
