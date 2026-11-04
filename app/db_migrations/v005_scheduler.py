"""Add durable scheduler tables without changing existing application records."""

import sqlite3

from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.scheduler.database_models import C_SCHEDULER_TABLES

C_BEGIN_TRANSACTION = "BEGIN IMMEDIATE"


def apply(connection: sqlite3.Connection) -> None:
    """Compile mapped DDL and keep all table/index creation in one rollbackable unit."""
    if not connection.in_transaction:
        connection.execute(C_BEGIN_TRANSACTION)
    for table in C_SCHEDULER_TABLES:
        connection.execute(str(CreateTable(table).compile(dialect=dialect())))
        for index in table.indexes:
            connection.execute(str(CreateIndex(index).compile(dialect=dialect())))
