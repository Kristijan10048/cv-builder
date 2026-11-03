"""Pydantic models used by the CV Builder API."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

C_MAX_JOB_SEARCH_RESULTS = 1000


class TemplateUpdate(BaseModel):
    cv: str = ""
    cover_letter: str = ""


class ApplicationInput(BaseModel):
    company: str = Field(min_length=1, max_length=250)
    job_title: str = Field(min_length=1, max_length=250)
    source_url: str = Field(default="", max_length=2000)
    job_description: str = Field(default="", max_length=100_000)
    adjusted_cv: str = Field(default="", max_length=200_000)
    adjusted_cover_letter: str = Field(default="", max_length=200_000)
    status: str = Field(default="Draft", max_length=50)
    notes: str = Field(default="", max_length=20_000)
    raw_html: str = Field(default="", max_length=5_000_000)
    imported_data: str = Field(default="", max_length=5_000_000)


class ImportInput(BaseModel):
    url: str = ""
    html: str = ""


class SettingsInput(BaseModel):
    lm_studio_url: str = Field(default="http://localhost:1234/v1", max_length=500)
    lm_studio_model: str = Field(default="", max_length=200)


class PersonalDetailsInput(BaseModel):
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=50)
    address_line1: str = Field(default="", max_length=250)
    address_line2: str = Field(default="", max_length=250)
    postal_code: str = Field(default="", max_length=30)
    city: str = Field(default="", max_length=120)
    state_region: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    nationality: str = Field(default="", max_length=120)
    date_of_birth: str = Field(default="", max_length=10)
    linkedin_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=500)
    current_company: str = Field(default="", max_length=250)
    current_job_title: str = Field(default="", max_length=250)
    work_authorization: str = Field(default="", max_length=250)
    notice_period: str = Field(default="", max_length=120)
    salary_expectation: str = Field(default="", max_length=120)
    strongest_programming_language: str = Field(default="", max_length=120)
    german_language_level: str = Field(default="", max_length=120)
    english_language_level: str = Field(default="", max_length=120)
    onsite_availability: str = Field(default="", max_length=20)
    travel_willingness: str = Field(default="", max_length=20)

    @field_validator("linkedin_url", "website_url")
    @classmethod
    def validate_optional_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("URLs must start with http:// or https://")
        return value


class JobSearchPreferenceInput(BaseModel):
    job_title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)
    ]
    country: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    radius_km: int = Field(default=0, ge=0, le=1000, strict=True)
    keywords: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    ] = Field(default_factory=list, max_length=30)
    posted_within_days: int | None = Field(default=None, ge=1, le=3650, strict=True)

    @model_validator(mode="after")
    def validate_radius_location(self):
        if self.radius_km and not self.city:
            raise ValueError("Enter a city when using a search radius.")
        return self


class GenerateInput(BaseModel):
    application_id: int
    document: str
    instructions: str = ""


JobBoard = Literal["linkedin", "indeed", "glassdoor", "zip_recruiter", "bayt", "bdjobs", "naukri"]


class JobSearchInput(BaseModel):
    """Validate a bounded per-board search independently of stored-page pagination."""

    preference_id: int = Field(gt=0, strict=True)
    sites: list[JobBoard] = Field(
        default_factory=lambda: ["linkedin", "indeed", "glassdoor", "zip_recruiter"],
        min_length=1, max_length=7,
    )
    # This bounds source postings before the adapter applies description keywords.
    results_wanted: int = Field(default=50, ge=1, le=C_MAX_JOB_SEARCH_RESULTS, strict=True)

    @field_validator("sites")
    @classmethod
    def unique_sites(cls, value):
        return list(dict.fromkeys(value))
