"""SQLAlchemy models for the tables maintained by ApplyKit's SQLite migrations."""

import json
from typing import Mapping

from sqlalchemy import ForeignKey, Integer, JSON, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class DatabaseModel(MappedAsDataclass, DeclarativeBase):
    """Share mapped dataclass metadata while leaving schema changes to migrations."""


class DocumentTemplateModel(DatabaseModel):
    """Represent a stored CV or cover-letter template."""

    __tablename__ = "document_templates"

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )
    filename: Mapped[str] = mapped_column(Text, default="")


class ApplicationModel(DatabaseModel):
    """Represent a saved application and its tailored documents."""

    __tablename__ = "applications"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(Text)
    job_title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, default="")
    job_description: Mapped[str] = mapped_column(Text, default="")
    adjusted_cv: Mapped[str] = mapped_column(Text, default="")
    adjusted_cover_letter: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="Draft")
    notes: Mapped[str] = mapped_column(Text, default="")
    raw_html: Mapped[str] = mapped_column(Text, default="")
    imported_data: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )


class SettingModel(DatabaseModel):
    """Represent a setting, including the JSON personal-details record."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class SchemaMigrationModel(DatabaseModel):
    """Represent a version recorded by the existing migration runner."""

    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    applied_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )


class JobSearchPreferenceModel(DatabaseModel):
    """Represent a saved search with its decoded description keywords."""

    __tablename__ = "job_search_preferences"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_title: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    radius_km: Mapped[int] = mapped_column(Integer)
    keywords: Mapped[list[str]] = mapped_column(JSON)
    posted_within_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )

    @classmethod
    def from_record(model_class, record: Mapping) -> "JobSearchPreferenceModel":
        """Decode a database row's JSON keywords into the model's search filters."""
        fields = dict(record)
        if isinstance(fields["keywords"], str):
            fields["keywords"] = json.loads(fields["keywords"])
        return model_class(**fields)


class AvailableJobModel(DatabaseModel):
    """Represent a board posting and its complete source data."""

    __tablename__ = "available_jobs"
    __table_args__ = (UniqueConstraint("site", "job_url"), {"sqlite_autoincrement": True})

    site: Mapped[str] = mapped_column(Text)
    job_url: Mapped[str] = mapped_column(Text)
    job_title: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    date_posted: Mapped[str | None] = mapped_column(Text, default=None)
    job_type: Mapped[str] = mapped_column(Text, default="")
    is_remote: Mapped[int | None] = mapped_column(Integer, default=None)
    raw_data: Mapped[str] = mapped_column(Text, default="{}")
    id: Mapped[int | None] = mapped_column(Integer, primary_key=True, nullable=False, default=None)
    first_fetched_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )
    fetched_at: Mapped[str] = mapped_column(
        Text,
        default="",
        insert_default=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )

    def to_stored_fields(self) -> dict:
        """Return insertable fields while leaving identity and timestamps to SQLite."""
        return {
            "site": self.site,
            "job_url": self.job_url,
            "job_title": self.job_title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "date_posted": self.date_posted,
            "job_type": self.job_type,
            "is_remote": self.is_remote,
            "raw_data": self.raw_data,
        }

    def to_list_item(self, applied: bool) -> dict:
        """Serialize the existing listing fields and convert SQLite flags to booleans."""
        return {
            "id": self.id,
            "site": self.site,
            "job_url": self.job_url,
            "job_title": self.job_title,
            "company": self.company,
            "location": self.location,
            "date_posted": self.date_posted,
            "job_type": self.job_type,
            "is_remote": None if self.is_remote is None else bool(self.is_remote),
            "first_fetched_at": self.first_fetched_at,
            "fetched_at": self.fetched_at,
            "applied": applied,
        }


class JobSearchResultModel(DatabaseModel):
    """Link an available posting to a saved search that found it."""

    __tablename__ = "job_search_results"

    preference_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_search_preferences.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("available_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def to_stored_fields(self) -> dict:
        """Return the composite key used to persist a search-to-posting link."""
        return {"preference_id": self.preference_id, "job_id": self.job_id}
