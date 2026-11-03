"""Disposable upgrade, transactional DDL failure, and matching-code rollback rehearsal."""

from contextlib import closing
import sqlite3

import pytest
from sqlalchemy import MetaData, insert, select

from app import database, db_migrations
from app.db_migrations import Migration, run_migrations
from app.db_migrations.v005_scheduler import apply as apply_scheduler
from app.db_migrations import v005_scheduler
from app.db_migrations.v006_scheduler_worker_table import C_LEGACY_WORKER_TABLE, apply as repair_worker_table
from app.database_models import ApplicationModel, AvailableJobModel, JobSearchPreferenceModel, SettingModel
from app.scheduler.database_models import C_SCHEDULER_TABLES, SchedulerWorkerModel
from app.scheduler.repository import ScheduleRepository
from app.scheduler.triggers import SystemClock

C_VERSION_FOUR_COUNT = 4
C_FAILING_VERSION = 5
C_FAILURE = "deliberate failure after schema creation"
C_SCHEMA_QUERY = "SELECT name FROM sqlite_master WHERE type = 'table'"
C_MIGRATION_QUERY = "SELECT version FROM schema_migrations ORDER BY version"
C_VERSION_FIVE_COUNT = 5
C_REPAIR_VERSION = 6
C_REPAIR_NAME = "scheduler_worker_table_name"
C_WORKER_ID = 1
C_OWNER_TOKEN = "retained-worker-owner"
C_WORKER_RECORD = {
    "started_at": "2026-11-01T12:00:00+00:00",
    "heartbeat_at": "2026-11-01T12:00:00+00:00",
    "stopped_at": "2026-11-01T12:01:00+00:00",
}


def test_version_four_upgrade_preserves_all_records_and_matching_restore(tmp_path, monkeypatch):
    """Back up stopped v4, upgrade a copy, verify data, and reopen the backup with v4 code."""
    migrations = db_migrations.MIGRATIONS
    legacy_migrations = migrations[:C_VERSION_FOUR_COUNT]
    monkeypatch.setattr(db_migrations, "MIGRATIONS", legacy_migrations)
    database.init_db()
    repository = ScheduleRepository()
    try:
        with repository.transaction(True) as connection:
            connection.execute(insert(ApplicationModel).values(id=1, company="Keep company", job_title="Keep role"))
            connection.execute(insert(JobSearchPreferenceModel).values(id=1, job_title="Keep search", country="Germany",
                                                                     city="Berlin", radius_km=0, keywords=["Python"], posted_within_days=1))
            connection.execute(insert(AvailableJobModel).values(site="linkedin", job_url="https://example.test/keep", job_title="Keep posting"))
            connection.execute(insert(SettingModel).values(key="scheduler-test-setting", value="Keep setting"))
        with repository.transaction() as connection:
            before = {table.name: connection.execute(select(table)).all() for table in (
                ApplicationModel.__table__, JobSearchPreferenceModel.__table__, AvailableJobModel.__table__, SettingModel.__table__,
            )}
        backup_path = tmp_path / "pre-upgrade.db"
        with closing(database.connect()) as source, closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)
        monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations)
        database.init_db()
        database.init_db()
        with repository.transaction() as connection:
            after = {table.name: connection.execute(select(table)).all() for table in (
                ApplicationModel.__table__, JobSearchPreferenceModel.__table__, AvailableJobModel.__table__, SettingModel.__table__,
            )}
        assert before == after
        monkeypatch.setattr(db_migrations, "MIGRATIONS", legacy_migrations)
        with closing(database.connect()) as upgraded:
            with pytest.raises(RuntimeError, match="unknown migration"):
                run_migrations(upgraded)
        with closing(sqlite3.connect(backup_path)) as restored:
            restored.row_factory = sqlite3.Row
            run_migrations(restored)
            assert len(restored.execute(C_MIGRATION_QUERY).fetchall()) == C_VERSION_FOUR_COUNT
    finally:
        repository.close()


def test_failed_scheduler_ddl_rolls_back_and_can_restart(monkeypatch):
    """No partial tables/version marker remain when migration fails after creating its schema."""
    migrations = db_migrations.MIGRATIONS
    monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations[:C_VERSION_FOUR_COUNT])
    database.init_db()

    def fail_after_creation(connection):
        """Fault injection after all new tables/indexes were created but before commit."""
        apply_scheduler(connection)
        raise RuntimeError(C_FAILURE)

    monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations[:C_VERSION_FOUR_COUNT] + (
        Migration(C_FAILING_VERSION, "task_scheduler", fail_after_creation),))
    with pytest.raises(RuntimeError, match=C_FAILURE):
        database.init_db()
    with closing(database.connect()) as connection:
        names = {row[0] for row in connection.execute(C_SCHEMA_QUERY)}
        assert not names.intersection(table.name for table in C_SCHEDULER_TABLES)
    monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations)
    database.init_db()
    with closing(database.connect()) as connection:
        assert len(connection.execute(C_MIGRATION_QUERY).fetchall()) == len(migrations)


@pytest.mark.parametrize("fail_before_commit", [False, True])
def test_legacy_worker_table_upgrade_preserves_health_and_rolls_back(monkeypatch, fail_before_commit):
    """Upgrade a recorded early v5 schema, retaining its row even after a failed rename."""
    migrations = db_migrations.MIGRATIONS
    legacy_table = SchedulerWorkerModel.__table__.to_metadata(MetaData(), name=C_LEGACY_WORKER_TABLE)
    legacy_tables = tuple(
        legacy_table if mapped_table is SchedulerWorkerModel.__table__ else mapped_table
        for mapped_table in C_SCHEDULER_TABLES
    )
    monkeypatch.setattr(v005_scheduler, "C_SCHEDULER_TABLES", legacy_tables)
    monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations[:C_VERSION_FIVE_COUNT])
    database.init_db()
    repository = ScheduleRepository()
    try:
        with repository.transaction(True) as connection:
            connection.execute(insert(legacy_table).values(
                id=C_WORKER_ID, owner_token=C_OWNER_TOKEN, record=C_WORKER_RECORD,
            ))

        def fail_after_rename(connection):
            """Simulate interruption before the repair migration's version is committed."""
            repair_worker_table(connection)
            raise RuntimeError(C_FAILURE)

        if fail_before_commit:
            monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations[:C_VERSION_FIVE_COUNT] + (
                Migration(C_REPAIR_VERSION, C_REPAIR_NAME, fail_after_rename),
            ))
            with pytest.raises(RuntimeError, match=C_FAILURE):
                database.init_db()
            with repository.transaction() as connection:
                assert connection.execute(select(legacy_table.c.record)).scalar_one() == C_WORKER_RECORD

        monkeypatch.setattr(db_migrations, "MIGRATIONS", migrations)
        database.init_db()
        database.init_db()
        with repository.transaction() as connection:
            assert connection.execute(select(SchedulerWorkerModel.record)).scalar_one() == C_WORKER_RECORD
            assert connection.execute(select(SchedulerWorkerModel.owner_token)).scalar_one() == C_OWNER_TOKEN
        assert repository.worker_status(SystemClock().now()).state == "stopped"
        with closing(database.connect()) as connection:
            assert C_LEGACY_WORKER_TABLE not in {row[0] for row in connection.execute(C_SCHEMA_QUERY)}
    finally:
        repository.close()
