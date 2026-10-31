"""Translate manual job-search requests and domain failures to the existing HTTP API."""

from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query

from .models import JobBoard, JobSearchInput
from .services.job_search_dependencies import JobSearchServiceFactory, scrape_jobs
from .services.job_search_errors import (
    AllBoardsFailedError, PreferenceDeletedError, PreferenceNotFoundError,
)
# Preserve existing imports for callers while reusable code lives outside this router.
from .services.job_search_service import JobSearchOutcome, JobSearchService

C_API_PREFIX = "/api"
C_API_TAG = "Job search"
C_SEARCH_ROUTE = "/job-search"
C_LIST_ROUTE = "/available-jobs"
C_NOT_FOUND_STATUS = 404
C_CONFLICT_STATUS = 409
C_GATEWAY_STATUS = 502
C_MESSAGE_KEY = "message"
C_WARNINGS_KEY = "warnings"
C_FIRST_PAGE = 1
C_MINIMUM_ID = 0
C_DEFAULT_PAGE_SIZE = 20
C_MAXIMUM_PAGE_SIZE = 100
C_MAXIMUM_SEARCH_LENGTH = 250
C_EMPTY_SEARCH = ""
C_ROUTER = APIRouter(prefix=C_API_PREFIX, tags=[C_API_TAG])


@contextmanager
def translate_search_errors() -> Iterator[None]:
    """Preserve legacy HTTP status and detail shapes at the transport boundary."""
    try:
        yield
    except PreferenceNotFoundError as exception:
        raise HTTPException(C_NOT_FOUND_STATUS, str(exception)) from exception
    except PreferenceDeletedError as exception:
        raise HTTPException(C_CONFLICT_STATUS, str(exception)) from exception
    except AllBoardsFailedError as exception:
        raise HTTPException(C_GATEWAY_STATUS, {
            C_MESSAGE_KEY: str(exception), C_WARNINGS_KEY: exception.warnings,
        }) from exception


@C_ROUTER.post(C_SEARCH_ROUTE)
def search_jobs(payload: JobSearchInput) -> dict:
    """Fetch and persist jobs, keeping the router's replaceable scraper test seam."""
    with translate_search_errors(), JobSearchServiceFactory(scraper=scrape_jobs).create() as service:
        return service.search(payload)


@C_ROUTER.get(C_LIST_ROUTE)
def list_jobs(
    page: int = Query(default=C_FIRST_PAGE, ge=C_FIRST_PAGE),
    page_size: int = Query(default=C_DEFAULT_PAGE_SIZE, ge=C_FIRST_PAGE, le=C_MAXIMUM_PAGE_SIZE),
    preference_id: int | None = Query(default=None, gt=C_MINIMUM_ID),
    site: JobBoard | None = None,
    search: str = Query(default=C_EMPTY_SEARCH, max_length=C_MAXIMUM_SEARCH_LENGTH),
) -> dict:
    """List stored jobs and deterministically dispose the request's repository."""
    with translate_search_errors(), JobSearchServiceFactory().create() as service:
        return service.repository.list_jobs(page, page_size, preference_id, site, search)
