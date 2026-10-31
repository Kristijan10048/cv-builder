"""Construct fetch dependencies explicitly and dispose only resources owned here."""

from contextlib import contextmanager
from typing import Callable, Iterator

from ..job_search_adapter import BaseJobBoardCoordinator, JobSearchAdapter
from ..job_search_repository import JobSearchRepository
from .job_search_service import JobSearchService


def scrape_jobs(**arguments):
    """Load JobSpy only when fetching, keeping service imports offline and lightweight."""
    from jobspy import scrape_jobs as scrape_jobspy_jobs

    return scrape_jobspy_jobs(**arguments)


class JobSearchServiceFactory:
    """Provide a scoped service while borrowing injected scraper/coordinator resources."""

    def __init__(
        self, scraper: Callable = scrape_jobs,
        coordinator: BaseJobBoardCoordinator | None = None,
        repository_factory: Callable[[], JobSearchRepository] = JobSearchRepository,
    ) -> None:
        """Accept replaceable construction dependencies without opening a database."""
        self.scraper = scraper
        self.coordinator = coordinator
        self.repository_factory = repository_factory

    @contextmanager
    def create(self, repository: JobSearchRepository | None = None) -> Iterator[JobSearchService]:
        """Dispose an owned repository even on construction/fetch failure; borrow injections."""
        owns_repository = repository is None
        search_repository = self.repository_factory() if owns_repository else repository
        try:
            adapter = JobSearchAdapter(self.scraper, self.coordinator)
            yield JobSearchService(search_repository, adapter)
        finally:
            if owns_repository:
                search_repository.close()
