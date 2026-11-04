"""Repair the worker table name used by early scheduler development databases."""

import sqlite3

from sqlalchemy import column, select, table
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import DDL

from app.scheduler.database_models import C_WORKER_TABLE

C_LEGACY_WORKER_TABLE = "scheduler_worker_state"
C_SCHEMA_TABLE = "sqlite_master"
C_NAME_COLUMN = "name"
C_TYPE_COLUMN = "type"
C_TABLE_TYPE = "table"
C_LITERAL_BINDS = "literal_binds"
C_BEGIN_TRANSACTION = "BEGIN IMMEDIATE"
C_RENAME_TABLE = "ALTER TABLE %(legacy)s RENAME TO %(current)s"
C_UNEXPECTED_SCHEMA = "Scheduler worker tables are missing or ambiguous; restore a consistent database before upgrading."


class WorkerTableMigration:
    """Rename only the known legacy table, preserving its health and ownership record."""

    def apply(self, connection: sqlite3.Connection) -> None:
        """Make current schemas a no-op and reject ambiguous schemas without deleting data."""
        if not connection.in_transaction:
            connection.execute(C_BEGIN_TRANSACTION)
        sqlite_dialect = dialect()
        schema = table(C_SCHEMA_TABLE, column(C_NAME_COLUMN), column(C_TYPE_COLUMN))
        statement = select(schema.c.name).where(schema.c.type == C_TABLE_TYPE)
        compiled = statement.compile(dialect=sqlite_dialect, compile_kwargs={C_LITERAL_BINDS: True})
        names = {record[0] for record in connection.execute(str(compiled))}
        legacy_exists = C_LEGACY_WORKER_TABLE in names
        current_exists = C_WORKER_TABLE in names
        if legacy_exists == current_exists:
            raise RuntimeError(C_UNEXPECTED_SCHEMA)
        if legacy_exists:
            # SQLite's transactional rename retains every row and constraint.
            preparer = sqlite_dialect.identifier_preparer
            rename = DDL(C_RENAME_TABLE, context={
                "legacy": preparer.quote(C_LEGACY_WORKER_TABLE),
                "current": preparer.quote(C_WORKER_TABLE),
            })
            connection.execute(str(rename.compile(dialect=sqlite_dialect)))


def apply(connection: sqlite3.Connection) -> None:
    """Run the compatibility repair inside the versioned migration transaction."""
    WorkerTableMigration().apply(connection)
