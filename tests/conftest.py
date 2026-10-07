"""Keep the complete test suite away from the user's local application database."""

import gc

import pytest

from app import database


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("APPLYKIT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("APPLYKIT_LOG_LEVEL", "INFO")
    yield
    # Existing API tests leave SQLite transaction contexts for garbage collection.
    gc.collect()
