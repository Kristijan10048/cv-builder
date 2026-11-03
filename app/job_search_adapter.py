"""Translate saved searches and JobSpy results without database or HTTP concerns."""

import json
import math
from abc import ABC, abstractmethod
from typing import Callable
from urllib.parse import urlsplit

from .database_models import AvailableJobModel, JobSearchPreferenceModel
from .job_search_glassdoor import C_GLASSDOOR_SITE, GlassdoorSearchGuard

C_KILOMETRES_PER_MILE = 1.609344
C_HOURS_PER_DAY = 24
C_HTTP_SCHEMES = frozenset({"http", "https"})
C_COUNTRY_REQUIRED_BOARDS = frozenset({"indeed", "glassdoor"})
C_ZIP_RECRUITER_COUNTRIES = frozenset({"USA", "CANADA"})
C_GLASSDOOR_GUARD = GlassdoorSearchGuard()
C_SITE_NAME_ARGUMENT = "site_name"
C_FIRST_SITE_INDEX = 0
C_COUNTRY_CODE_FIELD = "code"
C_COUNTRY_ISO3_FIELD = "iso3"
C_COUNTRY_NAME_FIELD = "name"
C_EMPTY_COUNTRY = ""
C_BANGLADESH_ALIASES = frozenset({"bangladesh", "bd", "bgd"})


class BaseJobBoardCoordinator(ABC):
    """Proposed SCH-02 seam for SCH-01/SCH-05 integration; not a frozen contract."""

    @abstractmethod
    def search(self, scraper: Callable, arguments: dict) -> tuple[object, str | None]:
        """Call one board under coordination, returning its frame and optional warning."""
        raise NotImplementedError


class LocalJobBoardCoordinator(BaseJobBoardCoordinator):
    """Preserve the current process-local Glassdoor guard until SCH-05 integration."""

    def search(self, scraper: Callable, arguments: dict) -> tuple[object, str | None]:
        """Use the replaceable Glassdoor guard and call other boards directly."""
        site = arguments[C_SITE_NAME_ARGUMENT][C_FIRST_SITE_INDEX]
        if site == C_GLASSDOOR_SITE:
            return C_GLASSDOOR_GUARD.search(scraper, arguments)
        return scraper(**arguments), None


class JobBoardSearchError(ValueError):
    """Carry accepted partial results alongside a user-facing board failure."""

    def __init__(self, warning: str, jobs: list[AvailableJobModel], skipped_count: int) -> None:
        """Retain postings fetched before a board stopped serving results."""
        super().__init__(warning)
        self.jobs = jobs
        self.skipped_count = skipped_count


class JobSearchAdapter:
    """Build board-specific requests and normalize returned JobSpy postings."""

    def __init__(self, scraper: Callable, coordinator: BaseJobBoardCoordinator | None = None):
        """Borrow a scraper and optional coordinator; callers retain resource ownership."""
        self.scraper = scraper
        self.coordinator = coordinator if coordinator is not None else LocalJobBoardCoordinator()

    def search_board(
        self, preference: JobSearchPreferenceModel, site: str, results_wanted: int,
    ) -> tuple[list[AvailableJobModel], int]:
        """Fetch one board and return accepted postings and incomplete-record count."""
        arguments = self.build_arguments(preference, site, results_wanted)
        result_frame, warning = self.coordinator.search(self.scraper, arguments)
        accepted_jobs, skipped_count = self.normalize_records(result_frame, site, preference.keywords)
        if warning:
            raise JobBoardSearchError(warning, accepted_jobs, skipped_count)
        return accepted_jobs, skipped_count

    @staticmethod
    def resolve_country(value: str):
        """Resolve JobSpy country names and common ISO codes, or return None."""
        # Keep JobSpy lazy-loaded so other application features can start without it.
        from jobspy.model import Country

        if not value:
            return None
        try:
            return Country(value)
        except ValueError:
            # JobSpy 1.4 no longer stores ISO aliases on its country enum.
            from .job_search_locations import get_location_catalog

            normalized_value = value.strip().casefold()
            for country_record in get_location_catalog().list_countries():
                aliases = (
                    country_record[C_COUNTRY_CODE_FIELD].casefold(),
                    country_record[C_COUNTRY_ISO3_FIELD].casefold(),
                )
                if normalized_value in aliases:
                    try:
                        return Country(country_record[C_COUNTRY_NAME_FIELD])
                    except ValueError:
                        return None
        return None

    def build_arguments(self, preference: JobSearchPreferenceModel, site: str, results_wanted: int) -> dict:
        """Validate board coverage and translate saved filters into JobSpy arguments."""
        country = self.resolve_country(preference.country)
        self.validate_country(site, country, preference.country)
        posted_within_days = preference.posted_within_days
        location_parts = [preference.city, preference.country]
        if site == C_GLASSDOOR_SITE and preference.city:
            # Glassdoor autocomplete needs the city alone; country_indeed selects its domain.
            location_parts = [preference.city]
        arguments = {
            "site_name": [site],
            "search_term": preference.job_title,
            "location": ", ".join(part for part in location_parts if part) or None,
            "results_wanted": results_wanted,
            "distance": math.ceil(preference.radius_km / C_KILOMETRES_PER_MILE),
            "hours_old": posted_within_days * C_HOURS_PER_DAY if posted_within_days else None,
            "fetch_description": True,
            "description_format": "plain",
            "verbose": 0,
        }
        if country:
            arguments["country_indeed"] = country.value
        return arguments

    @staticmethod
    def validate_country(site: str, country, selected_country: str = C_EMPTY_COUNTRY) -> None:
        """Raise the existing user-facing warning for unsupported board countries."""
        if site in C_COUNTRY_REQUIRED_BOARDS and (country is None or country.name == "WORLDWIDE"):
            raise ValueError("Set a supported country in this saved search for Indeed and Glassdoor.")
        if site == "glassdoor":
            from jobspy.glassdoor.constant import domains

            if country not in domains:
                raise ValueError("Glassdoor does not support this search's country.")
        # A selected country removed from JobSpy must not silently become its US default.
        if (site == "zip_recruiter" and (country is not None or selected_country)
                and (country is None or country.name not in C_ZIP_RECRUITER_COUNTRIES)):
            raise ValueError("ZipRecruiter supports searches in the US and Canada.")
        if (site == "naukri" and (country is not None or selected_country)
                and (country is None or country.name != "INDIA")):
            raise ValueError("Naukri supports searches in India.")
        if (site == "bdjobs" and selected_country
                and selected_country.strip().casefold() not in C_BANGLADESH_ALIASES):
            raise ValueError("BDJobs supports searches in Bangladesh.")

    @staticmethod
    def normalize_text(value) -> str:
        """Trim a source value while representing missing values as empty strings."""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def is_valid_url(job_url: str) -> bool:
        """Accept HTTP links with a hostname and without embedded credentials."""
        try:
            parsed_url = urlsplit(job_url)
            return bool(
                parsed_url.scheme in C_HTTP_SCHEMES
                and parsed_url.hostname
                and not parsed_url.username
                and not parsed_url.password
            )
        except ValueError:
            return False

    def normalize_records(
        self, result_frame, site: str, keywords: list[str],
    ) -> tuple[list[AvailableJobModel], int]:
        """Filter descriptions and convert complete source records to stored fields."""
        # Pandas JSON converts NaN/NaT and numpy scalars to JSON-safe values.
        source_records = json.loads(result_frame.to_json(orient="records", date_format="iso"))
        accepted_jobs = []
        skipped_count = 0
        normalized_keywords = [keyword.casefold() for keyword in keywords]
        for source_record in source_records:
            job_title = self.normalize_text(source_record.get("title"))
            job_url = self.normalize_text(source_record.get("job_url"))
            if not job_title or not self.is_valid_url(job_url):
                skipped_count += 1
                continue
            description = self.normalize_text(source_record.get("description"))
            normalized_description = description.casefold()
            if not all(keyword in normalized_description for keyword in normalized_keywords):
                continue
            date_posted = source_record.get("date_posted")
            remote_value = source_record.get("is_remote")
            accepted_jobs.append(AvailableJobModel(
                site=site,
                job_url=job_url,
                job_title=job_title,
                company=self.normalize_text(source_record.get("company")),
                location=self.normalize_text(source_record.get("location")),
                description=description,
                date_posted=self.normalize_text(date_posted)[:10] if date_posted else None,
                job_type=self.normalize_text(source_record.get("job_type")),
                is_remote=None if remote_value is None else int(bool(remote_value)),
                raw_data=json.dumps(source_record, ensure_ascii=False, allow_nan=False),
            ))
        return accepted_jobs, skipped_count
