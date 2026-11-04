"""Cross-process nonblocking board exclusion and durable Glassdoor cooldown."""

from datetime import timedelta
import logging
import math

import portalocker

from app.database_locking import DatabaseLock
from app.job_search_adapter import BaseJobBoardCoordinator, C_FIRST_SITE_INDEX, C_SITE_NAME_ARGUMENT
from app.job_search_glassdoor import (
    C_COOLDOWN_WARNING_TEMPLATE, C_GLASSDOOR_COOLDOWN_SECONDS, C_GLASSDOOR_LOGGER_NAME,
    C_GLASSDOOR_RATE_LIMIT_WARNING, C_GLASSDOOR_SITE, GlassdoorRateLimitCapture,
)
from app.scheduler import constants as scheduler_constants
from app.scheduler.triggers import SystemClock
from .job_search_errors import BoardUnavailableError

C_BUSY_STATUS = "busy"
C_COOLDOWN_STATUS = "cooldown"
C_BUSY_WARNING = "This board is being searched by another request. Try again later."


class SharedJobBoardCoordinator(BaseJobBoardCoordinator):
    """Coordinate the whole scrape and rate-limit capture across manual/worker calls."""

    def __init__(self, configuration, repository, clock=None):
        """Borrow storage; the service factory owns cleanup after all board threads drain."""
        self.configuration = configuration
        self.repository = repository
        self.clock = clock or SystemClock()

    def search(self, scraper, arguments):
        """Reject busy/cooling boards immediately and persist 429 even on scraper errors."""
        site = arguments[C_SITE_NAME_ARGUMENT][C_FIRST_SITE_INDEX]
        board_lock = DatabaseLock(self.configuration, scheduler_constants.C_LOCK_BOARD_PREFIX + site)
        try:
            board_lock.__enter__()
        except portalocker.exceptions.LockException as exception:
            raise BoardUnavailableError(C_BUSY_STATUS, C_BUSY_WARNING) from exception
        try:
            if site != C_GLASSDOOR_SITE:
                return scraper(**arguments), None
            deadline = self.repository.get_board_cooldown(site)
            now = self.clock.now()
            if deadline and deadline > now:
                raise BoardUnavailableError(C_COOLDOWN_STATUS, C_COOLDOWN_WARNING_TEMPLATE.format(
                    remaining_seconds=math.ceil((deadline - now).total_seconds())))
            capture = GlassdoorRateLimitCapture()
            board_logger = logging.getLogger(C_GLASSDOOR_LOGGER_NAME)
            board_logger.addHandler(capture)
            try:
                frame = scraper(**arguments)
            finally:
                board_logger.removeHandler(capture)
                capture.close()
                if capture.rate_limited:
                    self.repository.extend_board_cooldown(site, self.clock.now() + timedelta(seconds=C_GLASSDOOR_COOLDOWN_SECONDS))
            return frame, C_GLASSDOOR_RATE_LIMIT_WARNING if capture.rate_limited else None
        finally:
            board_lock.__exit__(None, None, None)
