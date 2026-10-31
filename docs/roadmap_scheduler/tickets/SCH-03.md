# SCH-03: Add scheduler persistence and safe startup

**Status:** Pending. **Depends on:** [SCH-01](SCH-01.md).
**Estimate:** 1.5–2.5 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

Schedules, run requests, results, and cooldowns survive restarts while web and
worker processes safely share the existing local database.

## Work and file ownership

- Create `app/scheduler/database_models.py`, `repository.py`, and `queries.py`
  using the existing `DatabaseModel` base. Map every table in the roadmap.
- Own the next migration module and registration in `app/db_migrations/__init__.py`;
  verify the next free version before naming it. Create tables/indexes through
  mapped schema definitions, with additive upgrade behavior and explicit rollback
  on failure. Do not rewrite migrations 1–4.
- Implement short atomic transactions for revision-checked edits, tombstones,
  idempotent manual requests, timed claims, input snapshots, run transitions,
  recovery, health, cooldown, and bounded terminal-history pruning.
- Enforce occurrence uniqueness and active-run exclusion in the database, not
  merely in Python. Keep manual dedupe separate from timed occurrence keys.
- Preserve history after schedule/preference removal; use nullable historical
  references plus snapshots where needed. Define a nullable preference FK on
  schedules and clear it on tombstoning so SCH-06 can permit later preference
  deletion while retaining history. Block live references transactionally.
- Update `app/database.py` for the SCH-01 database path settings, bounded busy
  timeout, and connection cleanup. Add `app/database_locking.py` for a shared
  migration lock, used by existing `init_db()` and future worker startup.
- Provide read/query methods needed by the API; do not edit routers or the
  existing job-search repository owned by SCH-02.

## Acceptance and validation

Create/run `tests/test_scheduler_repository.py` and
`tests/test_scheduler_migrations.py`. Cover fresh creation, version-4 upgrade,
preserved user records, repeated startup, failed migration recovery, unique
claims, competing revision updates, rollback, history retention, preference
reference policy, and database contention. Exercise the migration lock from two
processes against a disposable database; no lock remains held after failure.

Run existing migration and repository regressions. No test opens the user's
default database. No transaction stays open during network work.

**Handoff:** migration version, query/repository API, models, transaction guarantees,
temporary-database fixtures, and tested simultaneous-startup behavior.
