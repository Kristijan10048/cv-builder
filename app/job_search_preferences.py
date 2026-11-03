"""CRUD API for locally saved job search preferences."""

from contextlib import closing
import json
import sqlite3

from fastapi import APIRouter, HTTPException

from .database import connect
from .models import JobSearchPreferenceInput
from .job_search_repository import JobSearchRepository
from .services.job_search_errors import PreferenceNotFoundError
from .scheduler.repository import SchedulePreferenceDeletionGuard
from .scheduler.errors import SchedulerError
from .scheduler.api import error_response

C_PREFERENCE_NOT_FOUND_STATUS = 404

router = APIRouter(prefix="/api/job-search-preferences", tags=["Job search preferences"])
MAX_PREFERENCES = 10


def _preference(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["keywords"] = json.loads(data["keywords"])
    return data


def _get_preference(db: sqlite3.Connection, preference_id: int) -> dict:
    row = db.execute(
        "SELECT * FROM job_search_preferences WHERE id = ?", (preference_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Job search preference not found.")
    return _preference(row)


def _stored_fields(payload: JobSearchPreferenceInput) -> dict:
    data = payload.model_dump()
    data["keywords"] = json.dumps(data["keywords"], ensure_ascii=False)
    return data


@router.get("")
def list_preferences():
    with closing(connect()) as db:
        return [
            _preference(row)
            for row in db.execute("SELECT * FROM job_search_preferences ORDER BY id")
        ]


@router.get("/{preference_id}")
def get_preference(preference_id: int):
    with closing(connect()) as db:
        return _get_preference(db, preference_id)


@router.post("", status_code=201)
def create_preference(payload: JobSearchPreferenceInput):
    with closing(connect()) as db, db:
        # Serialize the count and insert so simultaneous requests cannot exceed ten.
        db.execute("BEGIN IMMEDIATE")
        count = db.execute("SELECT COUNT(*) FROM job_search_preferences").fetchone()[0]
        if count >= MAX_PREFERENCES:
            raise HTTPException(409, "You can save up to 10 job search preferences. Edit or delete an existing search first.")
        cursor = db.execute(
            """INSERT INTO job_search_preferences
               (job_title, country, city, radius_km, keywords, posted_within_days)
               VALUES (:job_title, :country, :city, :radius_km, :keywords, :posted_within_days)""",
            _stored_fields(payload),
        )
        return _get_preference(db, cursor.lastrowid)


@router.put("/{preference_id}")
def update_preference(preference_id: int, payload: JobSearchPreferenceInput):
    with closing(connect()) as db, db:
        cursor = db.execute(
            """UPDATE job_search_preferences
               SET job_title = :job_title, country = :country, city = :city,
                   radius_km = :radius_km, keywords = :keywords,
                   posted_within_days = :posted_within_days, updated_at = CURRENT_TIMESTAMP
               WHERE id = :id""",
            {**_stored_fields(payload), "id": preference_id},
        )
        if not cursor.rowcount:
            raise HTTPException(404, "Job search preference not found.")
        return _get_preference(db, preference_id)


@router.delete("/{preference_id}", status_code=204)
def delete_preference(preference_id: int):
    """Delete only when no live schedule references this preference, in one transaction."""
    repository = JobSearchRepository()
    try:
        repository.delete_preference(preference_id, SchedulePreferenceDeletionGuard())
    except SchedulerError as exception:
        return error_response(exception)
    except PreferenceNotFoundError as exception:
        raise HTTPException(C_PREFERENCE_NOT_FOUND_STATUS, str(exception)) from exception
    finally:
        repository.close()
