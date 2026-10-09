"""SQLAlchemy persistence for job searches using the existing SQLite schema."""

import math
import sqlite3

from fastapi import HTTPException
from sqlalchemy import create_engine, event, exists, func, or_, select
from sqlalchemy.dialects.sqlite import Insert, insert
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from .database import connect
from .database_models import ApplicationModel, AvailableJobModel, JobSearchPreferenceModel, JobSearchResultModel

C_APPLIED_STATUSES = ("Applied", "Interview", "Offer")
C_READ_TRANSACTION = "BEGIN"
C_WRITE_TRANSACTION = "BEGIN IMMEDIATE"
C_UPDATED_JOB_FIELDS = (
    "job_title",
    "company",
    "location",
    "description",
    "date_posted",
    "job_type",
    "is_remote",
    "raw_data",
)


class JobSearchQueryCatalog:
    """Build parameterized SQLAlchemy statements from the mapped table classes."""

    @staticmethod
    def get_preference_query(preference_id: int) -> Select:
        """Select a saved search with automatic JSON decoding for its keywords."""
        return select(JobSearchPreferenceModel.__table__).where(
            JobSearchPreferenceModel.id == preference_id,
        )

    @staticmethod
    def preference_exists_query(preference_id: int) -> Select:
        """Select a preference's identity for an existence check within a transaction."""
        return select(JobSearchPreferenceModel.id).where(
            JobSearchPreferenceModel.id == preference_id,
        )

    @staticmethod
    def upsert_job_query(job: AvailableJobModel) -> Insert:
        """Insert a posting or update its contents while retaining its identity."""
        statement = insert(AvailableJobModel.__table__).values(**job.to_stored_fields())
        updated_fields = {
            field_name: statement.excluded[field_name]
            for field_name in C_UPDATED_JOB_FIELDS
        }
        updated_fields["fetched_at"] = func.current_timestamp()
        return statement.on_conflict_do_update(
            index_elements=[AvailableJobModel.site, AvailableJobModel.job_url],
            set_=updated_fields,
        )

    @staticmethod
    def get_job_id_query(job: AvailableJobModel) -> Select:
        """Find a stored posting by its unique board and URL."""
        return select(AvailableJobModel.id).where(
            AvailableJobModel.site == job.site,
            AvailableJobModel.job_url == job.job_url,
        )

    @staticmethod
    def link_result_query(search_result: JobSearchResultModel) -> Insert:
        """Link a posting to a search without duplicating its existing association."""
        statement = insert(JobSearchResultModel.__table__).values(**search_result.to_stored_fields())
        return statement.on_conflict_do_nothing(
            index_elements=[JobSearchResultModel.preference_id, JobSearchResultModel.job_id],
        )

    @staticmethod
    def build_filters(preference_id: int | None, site: str | None, search: str) -> list[ColumnElement[bool]]:
        """Build shared filter expressions with user values bound by SQLAlchemy."""
        conditions = []
        if preference_id is not None:
            conditions.append(exists().where(
                JobSearchResultModel.job_id == AvailableJobModel.id,
                JobSearchResultModel.preference_id == preference_id,
            ))
        if site:
            conditions.append(AvailableJobModel.site == site)
        search_text = search.strip()
        if search_text:
            search_pattern = f"%{search_text}%"
            conditions.append(or_(
                AvailableJobModel.company.like(search_pattern),
                AvailableJobModel.job_title.like(search_pattern),
                AvailableJobModel.description.like(search_pattern),
            ))
        return conditions

    @staticmethod
    def count_jobs_query(conditions: list[ColumnElement[bool]]) -> Select:
        """Count the same filtered postings used by the listing statement."""
        return select(func.count()).select_from(AvailableJobModel).where(*conditions)

    @staticmethod
    def list_jobs_query(conditions: list[ColumnElement[bool]], page: int, page_size: int) -> Select:
        """Select a deterministic page with applied status from current applications."""
        applied_expression = exists().where(
            ApplicationModel.source_url == AvailableJobModel.job_url,
            ApplicationModel.status.in_(C_APPLIED_STATUSES),
        ).label("applied")
        return select(
            AvailableJobModel.id,
            AvailableJobModel.site,
            AvailableJobModel.job_url,
            AvailableJobModel.job_title,
            AvailableJobModel.company,
            AvailableJobModel.location,
            AvailableJobModel.date_posted,
            AvailableJobModel.job_type,
            AvailableJobModel.is_remote,
            AvailableJobModel.first_fetched_at,
            AvailableJobModel.fetched_at,
            applied_expression,
        ).where(*conditions).order_by(
            AvailableJobModel.fetched_at.desc(),
            AvailableJobModel.id.desc(),
        ).limit(page_size).offset((page - 1) * page_size)


class JobSearchRepository:
    """Store postings and read consistent pages with SQLAlchemy-managed transactions."""

    def __init__(self):
        """Create an engine using the existing connection factory and close-on-return pool."""
        self.query_catalog = JobSearchQueryCatalog()
        # The creator resolves the current database path for each connection, including tests.
        self.engine = create_engine("sqlite://", creator=self.create_connection, poolclass=NullPool)
        event.listen(self.engine, "begin", self.begin_transaction)

    @staticmethod
    def create_connection() -> sqlite3.Connection:
        """Keep existing foreign-key configuration and let SQLAlchemy control transactions."""
        connection = connect()
        connection.isolation_level = None
        return connection

    @staticmethod
    def begin_transaction(connection: Connection) -> None:
        """Begin an explicit read snapshot or acquire the SQLite write lock before checking."""
        # SQLite requires explicit transaction control to preserve read snapshots and write locks.
        # These are transaction commands; all data queries are built from SQLAlchemy models.
        if connection.get_execution_options().get("job_search_write", False):
            connection.exec_driver_sql(C_WRITE_TRANSACTION)
        else:
            connection.exec_driver_sql(C_READ_TRANSACTION)

    def preference_exists(self, connection: Connection, preference_id: int) -> bool:
        """Check a preference within the caller's transaction to avoid deletion races."""
        statement = self.query_catalog.preference_exists_query(preference_id)
        return connection.execute(statement).first() is not None

    def get_preference(self, preference_id: int) -> JobSearchPreferenceModel:
        """Read saved filters into the existing model interface with decoded keywords."""
        statement = self.query_catalog.get_preference_query(preference_id)
        with self.engine.begin() as connection:
            record = connection.execute(statement).mappings().first()
        if record is None:
            raise HTTPException(404, "Job search preference not found.")
        return JobSearchPreferenceModel.from_record(record)

    def save_jobs(self, preference_id: int, jobs: list[AvailableJobModel]) -> None:
        """Atomically upsert postings and link them to a still-existing saved search."""
        with self.engine.connect().execution_options(job_search_write=True) as connection:
            with connection.begin():
                # Acquire the lock before checking: the preference may be deleted during scraping.
                if not self.preference_exists(connection, preference_id):
                    raise HTTPException(409, "The saved search was deleted while fetching jobs.")
                for job in jobs:
                    self.save_job(connection, preference_id, job)

    def save_job(self, connection: Connection, preference_id: int, job: AvailableJobModel) -> None:
        """Update a posting and link it without changing its identity or initial timestamp."""
        connection.execute(self.query_catalog.upsert_job_query(job))
        job_id = connection.execute(self.query_catalog.get_job_id_query(job)).scalar_one()
        search_result = JobSearchResultModel(preference_id=preference_id, job_id=job_id)
        connection.execute(self.query_catalog.link_result_query(search_result))

    def list_jobs(self, page: int, page_size: int, preference_id: int | None, site: str | None, search: str) -> dict:
        """Return a consistent count and page with applied status from current applications."""
        conditions = self.query_catalog.build_filters(preference_id, site, search)
        count_statement = self.query_catalog.count_jobs_query(conditions)
        with self.engine.begin() as connection:
            if preference_id is not None and not self.preference_exists(connection, preference_id):
                raise HTTPException(404, "Job search preference not found.")
            total = connection.execute(count_statement).scalar_one()
            total_pages = max(1, math.ceil(total / page_size))
            page = min(page, total_pages)
            listing_statement = self.query_catalog.list_jobs_query(conditions, page, page_size)
            records = connection.execute(listing_statement).mappings().all()
        items = []
        for record in records:
            job_fields = dict(record)
            applied = bool(job_fields.pop("applied"))
            job = AvailableJobModel(**job_fields)
            items.append(job.to_list_item(applied))
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        }
