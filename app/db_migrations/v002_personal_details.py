"""Reserve a settings record for the Firefox autofill profile."""

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO settings(key, value) VALUES ('personal_details', '{}')"
    )

