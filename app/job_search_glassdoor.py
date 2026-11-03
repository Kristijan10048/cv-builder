"""Expose Glassdoor rate limits that the pinned JobSpy library only logs."""

import logging
import math
from threading import Lock
from time import monotonic
from typing import Callable

C_GLASSDOOR_COOLDOWN_SECONDS = 300
C_GLASSDOOR_SITE = "glassdoor"
C_GLASSDOOR_LOGGER_NAME = "jobspy.glassdoor"
C_RATE_LIMIT_LOG_MESSAGE = "response status code 429"
C_INITIAL_RETRY_AFTER = 0.0
C_MINIMUM_REMAINING_SECONDS = 0
C_COOLDOWN_WARNING_TEMPLATE = (
    "Glassdoor requests are paused after HTTP 429. "
    "Try again in {remaining_seconds} seconds or search the other boards."
)
C_GLASSDOOR_RATE_LIMIT_WARNING = (
    "Glassdoor rate-limited this search (HTTP 429). "
    "Glassdoor requests are paused for 5 minutes. Try again later or search the other boards."
)


class GlassdoorRateLimitCapture(logging.Handler):
    """Observe JobSpy's swallowed rate-limit failures without changing its handlers."""

    def __init__(self) -> None:
        """Capture errors from autocomplete and result-page requests."""
        super().__init__(level=logging.ERROR)
        self.rate_limited = False

    def emit(self, record: logging.LogRecord) -> None:
        """Recognize the HTTP status message emitted by the pinned Glassdoor scraper."""
        if C_RATE_LIMIT_LOG_MESSAGE in record.getMessage():
            self.rate_limited = True


class GlassdoorSearchGuard:
    """Serialize Glassdoor searches and pause new requests after an HTTP 429."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        """Accept a monotonic clock so cooldown checks can be tested without waiting."""
        self.clock = clock
        self.search_lock = Lock()
        self.retry_after = C_INITIAL_RETRY_AFTER

    def search(self, scraper: Callable, arguments: dict) -> tuple[object, str | None]:
        """Return source data with a rate-limit warning, or reject an active cooldown."""
        # JobSpy logs on its own worker threads, so overlapping Glassdoor calls
        # must be serialized to associate the captured status with this search.
        with self.search_lock:
            remaining_seconds = math.ceil(self.retry_after - self.clock())
            if remaining_seconds > C_MINIMUM_REMAINING_SECONDS:
                raise ValueError(C_COOLDOWN_WARNING_TEMPLATE.format(remaining_seconds=remaining_seconds))
            capture = GlassdoorRateLimitCapture()
            glassdoor_logger = logging.getLogger(C_GLASSDOOR_LOGGER_NAME)
            glassdoor_logger.addHandler(capture)
            try:
                result_frame = scraper(**arguments)
            finally:
                glassdoor_logger.removeHandler(capture)
                capture.close()
            if capture.rate_limited:
                self.retry_after = self.clock() + C_GLASSDOOR_COOLDOWN_SECONDS
                return result_frame, C_GLASSDOOR_RATE_LIMIT_WARNING
            return result_frame, None
