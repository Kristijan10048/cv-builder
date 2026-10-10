"""Coordinate concurrent job-board searches and expose the existing job-search API."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import json
import logging

from fastapi import APIRouter, HTTPException, Query

from .database_models import AvailableJobModel, JobSearchPreferenceModel
from .job_search_adapter import JobBoardSearchError, JobSearchAdapter
from .job_search_repository import JobSearchRepository
from .models import JobBoard, JobSearchInput
from .request_logging import TRACE as C_TRACE_LOG_LEVEL

C_ROUTER = APIRouter(prefix="/api", tags=["Job search"])
C_LOGGER = logging.getLogger(__name__)
C_BOARD_STATUS_KEY = "status"
C_PARTIAL_BOARD_STATUS = "partial"
C_BOARD_WARNING_TEMPLATE = "{site}: {warning}"
C_BOARD_INTERRUPTED_LOG_MESSAGE = (
    "job_search_board_interrupted preference_id=%s site=%s count=%d error=%s"
)


def scrape_jobs(**arguments):
    """Lazy-load JobSpy and retain a replaceable scraper entry point for offline tests."""
    # Other application features can start even when JobSpy needs installing.
    from jobspy import scrape_jobs as scrape_jobspy_jobs

    return scrape_jobspy_jobs(**arguments)


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
        self.boards[site] = {"status": "completed", "count": len(found_jobs)}
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
            self.warnings.append(f"{site}: skipped {skipped_count} incomplete postings.")

    def fail_board(self, site: str, warning: str) -> None:
        """Record one board's failure while retaining results from other boards."""
        self.boards[site] = {"status": "failed", "count": 0}
        self.warnings.append(f"{site}: {warning}")

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
        """Raise the existing gateway error if every board failed before persistence."""
        if all(board["status"] == "failed" for board in self.boards.values()):
            C_LOGGER.error(
                "job_search_failed preference_id=%s reason=all_boards_failed",
                self.preference_id,
            )
            raise HTTPException(502, {
                "message": "All job board searches failed. Previously fetched jobs are still available.",
                "warnings": self.warnings,
            })

    def to_response(self) -> dict:
        """Return the unchanged search response with a distinct posting count."""
        return {
            "preference_id": self.preference_id,
            "fetched": len({(job.site, job.job_url) for job in self.jobs}),
            "boards": self.boards,
            "warnings": sorted(self.warnings),
        }


class JobSearchService:
    """Coordinate board searches while delegating scraping and storage to their classes."""

    def __init__(self, repository: JobSearchRepository, adapter: JobSearchAdapter):
        """Accept explicit collaborators so orchestration has no SQL or scraping details."""
        self.repository = repository
        self.adapter = adapter

    def search(self, payload: JobSearchInput) -> dict:
        """Fetch independent boards, persist accepted jobs, and return the search summary."""
        preference = self.repository.get_preference(payload.preference_id)
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
            response["fetched"],
            json.dumps(response["boards"]),
            json.dumps(response["warnings"]),
        )
        return response

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
                except ValueError as exception:
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
                    outcome.fail_board(site, "the search failed. Try again later or check your connection.")
        return outcome


@C_ROUTER.post("/job-search")
def search_jobs(payload: JobSearchInput) -> dict:
    """Fetch and persist jobs for the requested saved search and boards."""
    service = JobSearchService(JobSearchRepository(), JobSearchAdapter(scrape_jobs))
    return service.search(payload)


@C_ROUTER.get("/available-jobs")
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    preference_id: int | None = Query(default=None, gt=0),
    site: JobBoard | None = None,
    search: str = Query(default="", max_length=250),
) -> dict:
    """List locally stored jobs with the existing filters, pagination, and applied flags."""
    repository = JobSearchRepository()
    return repository.list_jobs(page, page_size, preference_id, site, search)
