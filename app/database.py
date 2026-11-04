from pathlib import Path
from contextlib import closing
import sqlite3

from .db_migrations import run_migrations
from .database_locking import DatabaseLock, configuration_for_database
from .scheduler.configuration import SchedulerConfiguration
from .scheduler import constants as scheduler_constants

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = SchedulerConfiguration.from_environment().database_path
C_FOREIGN_KEYS_PRAGMA = "PRAGMA foreign_keys = ON"


def connect() -> sqlite3.Connection:
    """Open a bounded-wait connection at the shared configured database path."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=scheduler_constants.C_SQLITE_BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute(C_FOREIGN_KEYS_PRAGMA)
    return connection


def init_db() -> None:
    """Serialize web/worker upgrades before opening migration transactions."""
    configuration = configuration_for_database(DB_PATH)
    with DatabaseLock(configuration, scheduler_constants.C_LOCK_MIGRATION,
                      scheduler_constants.C_MIGRATION_LOCK_TIMEOUT_SECONDS):
        with closing(connect()) as db:
            run_migrations(db)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Detach an optional SQLite row for existing HTTP serializers."""
    return dict(row) if row else None
