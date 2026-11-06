"""Clean existing available-job titles without changing posting metadata."""

import sqlite3

from sqlalchemy import bindparam, select, update
from sqlalchemy.dialects.sqlite import dialect

from ..database_models import AvailableJobModel
from ..job_title_cleanup import RegexJobTitleCleaner

C_BEGIN_TRANSACTION = "BEGIN IMMEDIATE"
C_NAMED_PARAMETERS = "named"
C_RECORD_ID_PARAMETER = "record_id"
C_CLEANED_TITLE_PARAMETER = "cleaned_title"


class JobTitleCleanupMigration:
    """Backfill titles in the same transaction as the migration version marker."""

    def apply(self, connection: sqlite3.Connection) -> None:
        """Update only changed titles, retaining raw source data, timestamps, and links."""
        if not connection.in_transaction:
            connection.execute(C_BEGIN_TRANSACTION)
        sqlite_dialect = dialect(paramstyle=C_NAMED_PARAMETERS)
        selection = select(AvailableJobModel.id, AvailableJobModel.job_title)
        compiled_selection = selection.compile(dialect=sqlite_dialect)
        records = connection.execute(str(compiled_selection), compiled_selection.params).fetchall()
        cleaner = RegexJobTitleCleaner()
        changed_titles = []
        for record_id, job_title in records:
            cleaned_title = cleaner.clean(job_title)
            if cleaned_title != job_title:
                changed_titles.append({
                    C_RECORD_ID_PARAMETER: record_id,
                    C_CLEANED_TITLE_PARAMETER: cleaned_title,
                })
        if changed_titles:
            # Use bound SQLAlchemy statements on the runner's existing SQLite transaction.
            statement = update(AvailableJobModel.__table__).where(
                AvailableJobModel.id == bindparam(C_RECORD_ID_PARAMETER),
            ).values(job_title=bindparam(C_CLEANED_TITLE_PARAMETER))
            compiled_update = statement.compile(dialect=sqlite_dialect)
            connection.executemany(str(compiled_update), changed_titles)


def apply(connection: sqlite3.Connection) -> None:
    """Apply the title backfill through the versioned migration runner."""
    JobTitleCleanupMigration().apply(connection)
