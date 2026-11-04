"""Small, versioned SQLite migration runner for CV Builder."""

from collections.abc import Callable
from dataclasses import dataclass
import sqlite3

from .v001_initial_schema import apply as apply_v001
from .v002_personal_details import apply as apply_v002
from .v003_job_search_preferences import apply as apply_v003
from .v004_available_jobs import apply as apply_v004
from .v005_scheduler import apply as apply_v005
from .v006_scheduler_worker_table import apply as apply_v006

C_SCHEDULER_VERSION = 5
C_SCHEDULER_MIGRATION_NAME = "task_scheduler"
C_WORKER_TABLE_VERSION = 6
C_WORKER_TABLE_MIGRATION_NAME = "scheduler_worker_table_name"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


MIGRATIONS = (
    Migration(1, "initial_schema", apply_v001),
    Migration(2, "personal_details_setting", apply_v002),
    Migration(3, "job_search_preferences", apply_v003),
    Migration(4, "available_jobs", apply_v004),
    Migration(C_SCHEDULER_VERSION, C_SCHEDULER_MIGRATION_NAME, apply_v005),
    Migration(C_WORKER_TABLE_VERSION, C_WORKER_TABLE_MIGRATION_NAME, apply_v006),
)


def run_migrations(connection: sqlite3.Connection) -> None:
    """Apply each pending migration exactly once, in version order."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    connection.commit()

    recorded = {
        row["version"]: row["name"]
        for row in connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        )
    }

    known_versions = {migration.version for migration in MIGRATIONS}
    unknown_versions = set(recorded) - known_versions
    if unknown_versions:
        versions = ", ".join(str(version) for version in sorted(unknown_versions))
        raise RuntimeError(f"Database contains unknown migration version(s): {versions}")

    for migration in MIGRATIONS:
        recorded_name = recorded.get(migration.version)
        if recorded_name:
            if recorded_name != migration.name:
                raise RuntimeError(
                    f"Migration {migration.version} is recorded as {recorded_name!r}, "
                    f"expected {migration.name!r}."
                )
            continue

        try:
            migration.apply(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
