"""Store up to ten independent job search preferences."""

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE job_search_preferences (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               job_title TEXT NOT NULL CHECK(length(trim(job_title)) > 0),
               country TEXT NOT NULL DEFAULT '',
               city TEXT NOT NULL DEFAULT '',
               radius_km INTEGER NOT NULL DEFAULT 0 CHECK(radius_km BETWEEN 0 AND 1000),
               keywords TEXT NOT NULL DEFAULT '[]',
               posted_within_days INTEGER CHECK(posted_within_days BETWEEN 1 AND 3650),
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CHECK(radius_km = 0 OR length(trim(city)) > 0)
           )"""
    )
