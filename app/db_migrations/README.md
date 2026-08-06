# ApplyKit database migrations

`app.database.init_db()` runs every migration in this directory when ApplyKit starts. Applied versions are recorded in the `schema_migrations` table.

## Add a schema change

1. Create the next module, for example `v003_gmail_candidates.py`.
2. Export an `apply(connection)` function from that module.
3. Import the function in `app/db_migrations/__init__.py`.
4. Append a `Migration` entry with the next integer version and a permanent name.
5. Add tests for upgrading both a fresh database and the previous schema.

Example:

```python
"""Add a candidate review table."""

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE gmail_candidates (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               gmail_message_id TEXT NOT NULL UNIQUE
           )"""
    )
```

After a migration has been used, do not change its version, name, or behavior. Add a new migration for later corrections. The runner stops if it encounters an unknown version or a recorded version whose name does not match the application code.

