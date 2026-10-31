"""Job-fetch failures shared by manual routes and background callers."""

C_PREFERENCE_NOT_FOUND_MESSAGE = "Job search preference not found."
C_PREFERENCE_DELETED_MESSAGE = "The saved search was deleted while fetching jobs."
C_ALL_BOARDS_FAILED_MESSAGE = (
    "All job board searches failed. Previously fetched jobs are still available."
)


class JobSearchError(Exception):
    """Base failure for job-search business rules without transport status codes."""


class PreferenceNotFoundError(JobSearchError):
    """Indicate that a requested saved search does not exist."""

    def __init__(self) -> None:
        """Use the existing safe missing-preference message."""
        super().__init__(C_PREFERENCE_NOT_FOUND_MESSAGE)


class PreferenceDeletedError(JobSearchError):
    """Indicate deletion between fetching criteria and persisting results."""

    def __init__(self) -> None:
        """Use the existing safe concurrent-deletion message."""
        super().__init__(C_PREFERENCE_DELETED_MESSAGE)


class AllBoardsFailedError(JobSearchError):
    """Retain independent board warnings when no board completed successfully."""

    def __init__(self, warnings: list[str], boards: dict[str, dict]) -> None:
        """Copy failure diagnostics so callers can construct HTTP or task results."""
        super().__init__(C_ALL_BOARDS_FAILED_MESSAGE)
        self.warnings = list(warnings)
        self.boards = {site: dict(result) for site, result in boards.items()}
