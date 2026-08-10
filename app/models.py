"""Pydantic models used by the ApplyKit API."""

from pydantic import BaseModel, Field, field_validator


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


class GenerateInput(BaseModel):
    application_id: int
    document: str
    instructions: str = ""
