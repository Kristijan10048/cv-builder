"""Normalize gender markers in available-job titles before persistence."""

from abc import ABC, abstractmethod
import re

C_SPACE = " "
C_GENDER_MARKER_PATTERN = re.compile(
    r"\(\s*(?:m\s*/\s*w\s*/\s*d|f\s*/\s*m\s*/\s*d|all\s+genders)\s*\)"
    r"|(?<!\w)(?:m\s*/\s*w\s*/\s*d|f\s*/\s*m\s*/\s*d)(?!\w)",
    re.IGNORECASE,
)


class BaseJobTitleCleaner(ABC):
    """Define title normalization shared by persistence and data migrations."""

    @abstractmethod
    def clean(self, job_title: str) -> str:
        """Return a title without irrelevant gender markers."""
        raise NotImplementedError


class RegexJobTitleCleaner(BaseJobTitleCleaner):
    """Remove supported gender markers anywhere while retaining other title text."""

    def clean(self, job_title: str) -> str:
        """Remove markers and collapse resulting whitespace without joining words."""
        cleaned_title, replacement_count = C_GENDER_MARKER_PATTERN.subn(C_SPACE, job_title)
        if not replacement_count:
            return job_title
        # A space keeps adjacent words separate when a marker had no surrounding spaces.
        return C_SPACE.join(cleaned_title.split())
