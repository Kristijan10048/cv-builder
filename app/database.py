from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cv_builder.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS document_templates (
                kind TEXT PRIMARY KEY CHECK(kind IN ('cv', 'cover_letter')),
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS applications (
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
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO document_templates(kind, content)
            VALUES ('cv', ''), ('cover_letter', '');

            INSERT OR IGNORE INTO settings(key, value)
            VALUES
                ('lm_studio_url', 'http://localhost:1234/v1'),
                ('lm_studio_model', '');
            """
        )
        template_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(document_templates)")
        }
        if "filename" not in template_columns:
            db.execute(
                "ALTER TABLE document_templates ADD COLUMN filename TEXT NOT NULL DEFAULT ''"
            )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None
