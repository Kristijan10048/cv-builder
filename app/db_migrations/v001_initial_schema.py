"""Create the original ApplyKit schema and upgrade legacy databases."""

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS document_templates (
               kind TEXT PRIMARY KEY CHECK(kind IN ('cv', 'cover_letter')),
               content TEXT NOT NULL DEFAULT '',
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS applications (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               company TEXT NOT NULL,
               job_title TEXT NOT NULL,
               source_url TEXT NOT NULL DEFAULT '',
               job_description TEXT NOT NULL DEFAULT '',
               adjusted_cv TEXT NOT NULL DEFAULT '',
               adjusted_cover_letter TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL DEFAULT 'Draft',
               notes TEXT NOT NULL DEFAULT '',
               raw_html TEXT NOT NULL DEFAULT '',
               imported_data TEXT NOT NULL DEFAULT '',
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS settings (
               key TEXT PRIMARY KEY,
               value TEXT NOT NULL
           )"""
    )

    template_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(document_templates)")
    }
    if "filename" not in template_columns:
        connection.execute(
            "ALTER TABLE document_templates "
            "ADD COLUMN filename TEXT NOT NULL DEFAULT ''"
        )

    connection.executemany(
        "INSERT OR IGNORE INTO document_templates(kind, content) VALUES (?, '')",
        (("cv",), ("cover_letter",)),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
        (
            ("lm_studio_url", "http://localhost:1234/v1"),
            ("lm_studio_model", ""),
        ),
    )

