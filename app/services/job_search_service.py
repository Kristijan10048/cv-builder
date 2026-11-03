"""Reusable concurrent job fetching without routes or HTTP exceptions."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
import json
import logging
from typing import Callable

from ..database_models import AvailableJobModel, JobSearchPreferenceModel
from ..job_search_adapter import JobBoardSearchError, JobBoardValidationError, JobSearchAdapter
from ..job_search_repository import BasePreferenceDeletionGuard, JobSearchRepository
from ..models import JobSearchInput
from .job_search_errors import AllBoardsFailedError, BoardUnavailableError

# Preserve the existing logging category used by manual-fetch diagnostics.
C_LOGGER_NAME = "app.job_search"
C_TRACE_LOG_LEVEL = 5
C_LOGGER = logging.getLogger(C_LOGGER_NAME)
C_BOARD_STATUS_KEY = "status"
C_PARTIAL_BOARD_STATUS = "partial"
C_COMPLETED_BOARD_STATUS = "completed"
C_FAILED_BOARD_STATUS = "failed"
C_UNAVAILABLE_BOARD_STATUSES = frozenset({C_FAILED_BOARD_STATUS, "busy", "cooldown"})
C_COUNT_KEY = "count"
C_PREFERENCE_ID_KEY = "preference_id"
C_FETCHED_KEY = "fetched"
C_BOARDS_KEY = "boards"
C_WARNINGS_KEY = "warnings"
C_ZERO_RESULTS = 0
C_BOARD_WARNING_TEMPLATE = "{site}: {warning}"
C_SKIPPED_WARNING_TEMPLATE = "{site}: skipped {skipped_count} incomplete postings."
C_SEARCH_FAILURE_WARNING = "the search failed. Try again later or check your connection."
C_BOARD_INTERRUPTED_LOG_MESSAGE = (
    "job_search_board_interrupted preference_id=%s site=%s count=%d error=%s"
)


class JobSearchOutcome:
    """Collect postings, independent board statuses, warnings, and search diagnostics."""

    def __init__(self, preference_id: int):
        """Initialize the outcome for one saved search without discarding stored jobs."""
        self.preference_id = preference_id
        self.jobs: list[AvailableJobModel] = []
        self.boards: dict[str, dict] = {}
        self.warnings: list[str] = []

    def complete_board(self, site: str, found_jobs: list[AvailableJobModel], skipped_count: int) -> None:
        """Keep accepted postings and log a successful board, including incomplete records."""
        self.jobs.extend(found_jobs)
        self.boards[site] = {C_BOARD_STATUS_KEY: C_COMPLETED_BOARD_STATUS, C_COUNT_KEY: len(found_jobs)}
        C_LOGGER.info(
            "job_search_board_completed preference_id=%s site=%s count=%d skipped=%d",
            self.preference_id,
            site,
            len(found_jobs),
            skipped_count,
        )
        if C_LOGGER.isEnabledFor(C_TRACE_LOG_LEVEL):
            for job in found_jobs:
                C_LOGGER.log(
                    C_TRACE_LOG_LEVEL,
                    "job_search_result preference_id=%s site=%s job=%s",
                    self.preference_id,
                    site,
                    json.dumps(job.to_stored_fields(), ensure_ascii=False),
                )
        if skipped_count:
            self.warnings.append(C_SKIPPED_WARNING_TEMPLATE.format(site=site, skipped_count=skipped_count))

    def fail_board(self, site: str, warning: str) -> None:
        """Record one board's failure while retaining results from other boards."""
        self.boards[site] = {C_BOARD_STATUS_KEY: C_FAILED_BOARD_STATUS, C_COUNT_KEY: C_ZERO_RESULTS}
        self.warnings.append(C_BOARD_WARNING_TEMPLATE.format(site=site, warning=warning))

    def interrupt_board(self, site: str, exception: JobBoardSearchError) -> None:
        """Keep accepted postings while exposing a failed or incomplete source request."""
        if exception.jobs:
            self.complete_board(site, exception.jobs, exception.skipped_count)
            self.boards[site][C_BOARD_STATUS_KEY] = C_PARTIAL_BOARD_STATUS
            self.warnings.append(C_BOARD_WARNING_TEMPLATE.format(site=site, warning=exception))
        else:
            self.fail_board(site, str(exception))
        C_LOGGER.warning(
            C_BOARD_INTERRUPTED_LOG_MESSAGE,
            self.preference_id, site, len(exception.jobs), exception,
        )

    def ensure_success(self) -> None:
        """Raise a domain failure if every board failed before persistence."""
        if all(board[C_BOARD_STATUS_KEY] in C_UNAVAILABLE_BOARD_STATUSES for board in self.boards.values()):
            C_LOGGER.error(
                "job_search_failed preference_id=%s reason=all_boards_failed",
                self.preference_id,
            )
            raise AllBoardsFailedError(self.warnings, self.boards)

    def to_response(self) -> dict:
        """Return the unchanged search response with a distinct posting count."""
        return {
            C_PREFERENCE_ID_KEY: self.preference_id,
            C_FETCHED_KEY: len({(job.site, job.job_url) for job in self.jobs}),
            C_BOARDS_KEY: self.boards,
            C_WARNINGS_KEY: sorted(self.warnings),
        }


class JobSearchService:
    """Coordinate board searches while delegating scraping and storage to their classes."""

    def __init__(self, repository: JobSearchRepository, adapter: JobSearchAdapter):
        """Borrow collaborators; their creator owns cleanup after all fetches finish."""
        self.repository = repository
        self.adapter = adapter

    def search(self, payload: JobSearchInput) -> dict:
        """Preserve the existing manual response using the reusable fetch operation."""
        return self.fetch(payload).to_response()

    def fetch(
        self, payload: JobSearchInput,
        on_preference: Callable[[JobSearchPreferenceModel], None] | None = None,
    ) -> JobSearchOutcome:
        """Capture effective criteria, fetch boards, then return the persisted outcome."""
        preference = self.repository.get_preference(payload.preference_id)
        if on_preference is not None:
            # Persist the effective snapshot before any board starts; failures abort fetching.
            on_preference(deepcopy(preference))
        C_LOGGER.info(
            "job_search_started preference_id=%s sites=%s results_wanted=%d preference=%s",
            payload.preference_id,
            json.dumps(payload.sites),
            payload.results_wanted,
            json.dumps(asdict(preference), ensure_ascii=False),
        )
        outcome = self.search_boards(preference, payload)
        outcome.ensure_success()
        self.repository.save_jobs(payload.preference_id, outcome.jobs)
        response = outcome.to_response()
        C_LOGGER.info(
            "job_search_completed preference_id=%s fetched=%d boards=%s warnings=%s",
            payload.preference_id,
            response[C_FETCHED_KEY],
            json.dumps(response[C_BOARDS_KEY]),
            json.dumps(response[C_WARNINGS_KEY]),
        )
        return outcome

    def search_boards(self, preference: JobSearchPreferenceModel, payload: JobSearchInput) -> JobSearchOutcome:
        """Run boards concurrently and isolate errors without losing successful results."""
        outcome = JobSearchOutcome(payload.preference_id)
        with ThreadPoolExecutor(max_workers=len(payload.sites)) as executor:
            board_futures = {
                executor.submit(self.adapter.search_board, preference, site, payload.results_wanted): site
                for site in payload.sites
            }
            for board_future in as_completed(board_futures):
                site = board_futures[board_future]
                try:
                    found_jobs, skipped_count = board_future.result()
                    outcome.complete_board(site, found_jobs, skipped_count)
                except JobBoardSearchError as exception:
                    outcome.interrupt_board(site, exception)
                except BoardUnavailableError as exception:
                    outcome.fail_board(site, str(exception))
                    outcome.boards[site][C_BOARD_STATUS_KEY] = exception.status
                except JobBoardValidationError as exception:
                    C_LOGGER.warning(
                        "job_search_board_failed preference_id=%s site=%s error=%s",
                        payload.preference_id,
                        site,
                        exception,
                    )
                    outcome.fail_board(site, str(exception))
                except Exception:
                    C_LOGGER.exception(
                        "job_search_board_failed preference_id=%s site=%s",
                        payload.preference_id,
                        site,
                    )
                    outcome.fail_board(site, C_SEARCH_FAILURE_WARNING)
        return outcome


class JobSearchPreferenceService:
    """Expose saved-search validation and transactional deletion to SCH-05/SCH-06."""

    def __init__(self, repository: JobSearchRepository) -> None:
        """Borrow storage without opening connections or importing transport modules."""
        self.repository = repository

    def get_preference(self, preference_id: int) -> JobSearchPreferenceModel:
        """Return detached current criteria or raise the shared missing-preference error."""
        return self.repository.get_preference(preference_id)

    def validate_search(self, payload: JobSearchInput) -> JobSearchPreferenceModel:
        """Validate every selected board against the saved country without scraping."""
        preference = self.get_preference(payload.preference_id)
        country = JobSearchAdapter.resolve_country(preference.country)
        for site in payload.sites:
            JobSearchAdapter.validate_country(site, country, preference.country)
        return preference

    def delete_preference(
        self, preference_id: int, guard: BasePreferenceDeletionGuard | None = None,
    ) -> None:
        """Delegate deletion and its optional policy to one serialized storage transaction."""
        self.repository.delete_preference(preference_id, guard)
