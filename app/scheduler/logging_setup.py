"""Worker-only rotating diagnostics without scraped content or saved personal criteria."""

import logging
from logging.handlers import RotatingFileHandler

from . import constants as scheduler_constants

C_SCHEDULER_LOGGER = "app.scheduler"
C_SEARCH_LOGGER = "app.job_search"
C_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class WorkerLogging:
    """Scope a dedicated safe sink and suppress verbose service/scraper diagnostics."""

    def __init__(self, configuration):
        """Prepare logging without touching application logging handlers."""
        self.configuration = configuration
        self.handler = None
        self.saved = []
        self.search_logger_disabled = None

    def __enter__(self):
        """Open the rotating worker file and isolate the scheduler logging hierarchy."""
        self.configuration.log_directory.mkdir(parents=True, exist_ok=True)
        self.handler = RotatingFileHandler(self.configuration.log_path,
                                          maxBytes=scheduler_constants.C_LOG_MAX_BYTES,
                                          backupCount=scheduler_constants.C_LOG_BACKUP_COUNT,
                                          encoding=scheduler_constants.C_PATH_ENCODING)
        self.handler.setFormatter(logging.Formatter(C_LOG_FORMAT))
        logger = logging.getLogger(C_SCHEDULER_LOGGER)
        self.saved.append((logger, logger.level, logger.propagate))
        logger.setLevel(scheduler_constants.C_LOG_LEVEL)
        logger.propagate = False
        logger.addHandler(self.handler)
        # Service diagnostics include saved criteria at INFO and postings at TRACE.
        # Disable that category in the standalone worker, including inherited sinks.
        search_logger = logging.getLogger(C_SEARCH_LOGGER)
        self.search_logger_disabled = search_logger.disabled
        search_logger.disabled = True
        return self

    def __exit__(self, exception_type, exception, traceback):
        """Close the worker sink and restore logger settings for embedded tests."""
        logging.getLogger(C_SCHEDULER_LOGGER).removeHandler(self.handler)
        self.handler.close()
        logging.getLogger(C_SEARCH_LOGGER).disabled = self.search_logger_disabled
        for logger, level, propagate in self.saved:
            logger.setLevel(level)
            logger.propagate = propagate
