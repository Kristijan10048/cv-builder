"""Store scraped postings and the saved searches that found them."""

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE available_jobs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               site TEXT NOT NULL,
               job_url TEXT NOT NULL,
               job_title TEXT NOT NULL,
               company TEXT NOT NULL DEFAULT '',
               location TEXT NOT NULL DEFAULT '',
               description TEXT NOT NULL DEFAULT '',
               date_posted TEXT,
               job_type TEXT NOT NULL DEFAULT '',
               is_remote INTEGER,
               raw_data TEXT NOT NULL DEFAULT '{}',
               first_fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               UNIQUE(site, job_url)
           )"""
    )
    connection.execute(
        """CREATE TABLE job_search_results (
               preference_id INTEGER NOT NULL REFERENCES job_search_preferences(id) ON DELETE CASCADE,
               job_id INTEGER NOT NULL REFERENCES available_jobs(id) ON DELETE CASCADE,
               PRIMARY KEY(preference_id, job_id)
           )"""
    )
    connection.execute("CREATE INDEX available_jobs_fetched ON available_jobs(fetched_at DESC, id DESC)")
    connection.execute("CREATE INDEX job_search_results_job ON job_search_results(job_id)")
