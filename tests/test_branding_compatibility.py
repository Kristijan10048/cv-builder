"""Regression checks for configuration continuity during the project rename."""

import logging
from pathlib import Path

import pytest

from app import request_logging
from app.scheduler import constants as scheduler_constants
from app.scheduler.configuration import SchedulerConfiguration
from app.scheduler.errors import SchedulerConfigurationError

C_DATABASE = "existing.db"
C_LOCKS = "existing-locks"
C_LOGS = "existing-logs"
C_WORKERS = "3"
C_POLL_SECONDS = "7"
C_RETENTION_DAYS = "30"
C_INVALID_VALUE = ""
C_DEBUG = "DEBUG"
C_INFO = "INFO"
C_LOGGER_NAME = "app"
C_NEW_LOGS = "new-logs"


class TestBrandingCompatibility:
    """Keep saved paths and logging behavior usable under either naming scheme."""

    def test_scheduler_aliases_preserve_all_settings(self, tmp_path):
        """Old names resolve to the same configuration as canonical names."""
        canonical_settings = {
            scheduler_constants.C_ENV_DATABASE_PATH: C_DATABASE,
            scheduler_constants.C_ENV_LOCK_DIR: C_LOCKS,
            scheduler_constants.C_ENV_LOG_DIR: C_LOGS,
            scheduler_constants.C_ENV_MAX_WORKERS: C_WORKERS,
            scheduler_constants.C_ENV_POLL_SECONDS: C_POLL_SECONDS,
            scheduler_constants.C_ENV_RETENTION_DAYS: C_RETENTION_DAYS,
        }
        legacy_settings = {
            scheduler_constants.C_LEGACY_ENVIRONMENT_NAMES[name]: value
            for name, value in canonical_settings.items()
        }
        assert SchedulerConfiguration.from_environment(legacy_settings, tmp_path) == (
            SchedulerConfiguration.from_environment(canonical_settings, tmp_path)
        )

    def test_canonical_scheduler_value_is_validated_before_alias(self, tmp_path):
        """An invalid new value must not fall back to an old valid value."""
        settings = {
            scheduler_constants.C_ENV_MAX_WORKERS: C_INVALID_VALUE,
            scheduler_constants.C_LEGACY_ENVIRONMENT_NAMES[
                scheduler_constants.C_ENV_MAX_WORKERS
            ]: C_WORKERS,
        }
        with pytest.raises(SchedulerConfigurationError):
            SchedulerConfiguration.from_environment(settings, tmp_path)

    def test_logging_aliases_and_canonical_precedence(self, tmp_path, monkeypatch):
        """Old log settings work while explicitly supplied new settings win."""
        monkeypatch.delenv(request_logging.C_ENV_LOG_DIRECTORY, raising=False)
        monkeypatch.delenv(request_logging.C_ENV_LOG_LEVEL, raising=False)
        monkeypatch.setenv(request_logging.C_LEGACY_ENV_LOG_DIRECTORY, str(tmp_path))
        monkeypatch.setenv(request_logging.C_LEGACY_ENV_LOG_LEVEL, C_DEBUG)
        handler = request_logging.configure_logging()
        try:
            assert Path(handler.baseFilename) == tmp_path / request_logging.C_LOG_FILENAME
            assert logging.getLogger(C_LOGGER_NAME).level == logging.DEBUG
        finally:
            request_logging.close_logging(handler)

        canonical_directory = tmp_path / C_NEW_LOGS
        monkeypatch.setenv(request_logging.C_ENV_LOG_DIRECTORY, str(canonical_directory))
        monkeypatch.setenv(request_logging.C_ENV_LOG_LEVEL, C_INFO)
        handler = request_logging.configure_logging()
        try:
            assert Path(handler.baseFilename) == canonical_directory / request_logging.C_LOG_FILENAME
            assert logging.getLogger(C_LOGGER_NAME).level == logging.INFO
        finally:
            request_logging.close_logging(handler)
