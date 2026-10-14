"""Verify explicit language extraction and its stored-job API integration."""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import update

from app.database_models import AvailableJobModel
from app.job_language_requirements import RegexLanguageRequirementExtractor
from app.job_search_repository import JobSearchRepository
from app.main import app

C_REQUIRED_LANGUAGES = "language_requirements"
C_GERMAN_REQUIREMENT = "German language skills: B2. English is required."
C_OPTIONAL_LANGUAGE = "German is preferred. We work with English clients."
C_REVISED_REQUIREMENT = "Fluent in Dutch."
C_DESCRIPTION_CASES = (
    (None, []),
    ("", []),
    ("Build Python and SQL services in Berlin, Germany.", []),
    ("Fluent in English and German.", ["English", "German"]),
    ("Fluency in written and spoken English.", ["English"]),
    ("Excellent command of English.", ["English"]),
    ("Good knowledge of French and Spanish.", ["French", "Spanish"]),
    ("English is required; German is optional.", ["English"]),
    ("English is required, German is preferred.", ["English"]),
    ("English required and German preferred.", ["English"]),
    ("English is required, no German is required.", ["English"]),
    ("No German required but English is essential.", ["English"]),
    ("You must speak Dutch.", ["Dutch"]),
    ("You must have English language skills.", ["English"]),
    ("English and French are mandatory.", ["English", "French"]),
    ("GERMAN (B2) and ENGLISH (C1) required.", ["German", "English"]),
    ("B2 German; English at least C1.", ["German", "English"]),
    (C_GERMAN_REQUIREMENT, ["German", "English"]),
    ("German is required. Fluent in German and English.", ["German", "English"]),
    ("Sehr gute Deutschkenntnisse und gute Englischkenntnisse.", ["German", "English"]),
    ("Deutschkenntnisse erforderlich. Englisch ist zwingend.", ["German", "English"]),
    ("Du sprichst fließend Deutsch und Englisch.", ["German", "English"]),
    ("Vloeiend Nederlands en Engels.", ["Dutch", "English"]),
    ("Nederlands is vereist.", ["Dutch"]),
    ("Fluent in Mandarin and Japanese.", ["Chinese", "Japanese"]),
    ("Knowledge of Polish, Italian and Portuguese.", ["Polish", "Italian", "Portuguese"]),
    ("English-speaking team in a German office.", []),
    ("The English documentation is required reading.", []),
    ("We offer English language courses and work with German clients.", []),
    ("English is the working language of our team.", []),
    ("Fluent in English preferred.", []),
    ("Good German skills are a plus.", []),
    ("German B2 would be an advantage.", []),
    ("Knowledge of French is nice-to-have.", []),
    ("German is not required.", []),
    ("No knowledge of German is necessary.", []),
    ("Fließende Deutschkenntnisse sind nicht erforderlich.", []),
    ("Goede kennis van Nederlands is een pluspunt.", []),
    (C_OPTIONAL_LANGUAGE, []),
    ("<ul><li>Fluent in <strong>German</strong> &amp; English.</li>"
     "<li>French is preferred.</li></ul>", ["German", "English"]),
    ("<p>Fluent in German</p><p>English preferred</p>", ["German"]),
    ("<script>English required</script><style>German required</style>", []),
    ("**English** is required.", ["English"]),
)


class TestLanguageRequirementExtraction:
    """Cover positive requirements and conservative rejection of unsupported evidence."""

    @pytest.mark.parametrize("description, expected_languages", C_DESCRIPTION_CASES)
    def test_explicit_requirements(self, description, expected_languages) -> None:
        """Extract named requirements without guessing from benefits or location."""
        assert RegexLanguageRequirementExtractor().extract(description) == expected_languages


class TestAvailableJobLanguageRequirements:
    """Ensure existing stored briefs supply the new column and refreshed briefs update it."""

    def test_stored_descriptions_are_parsed_without_refetch_or_schema_changes(self) -> None:
        """Read saved descriptions on listing and omit the full description from responses."""
        with TestClient(app) as api_client:
            preference_response = api_client.post(
                "/api/job-search-preferences", json={"job_title": "Developer"},
            )
            assert preference_response.status_code == 201
            preference_id = preference_response.json()["id"]
            repository = JobSearchRepository()
            stored_job = AvailableJobModel(
                site="indeed",
                job_url="https://example.test/language-required",
                job_title="Developer",
                description=C_GERMAN_REQUIREMENT,
            )
            optional_job = AvailableJobModel(
                site="linkedin",
                job_url="https://example.test/language-optional",
                job_title="Engineer",
                description=C_OPTIONAL_LANGUAGE,
            )
            repository.save_jobs(preference_id, [stored_job, optional_job])
            listing_response = api_client.get("/api/available-jobs")
            assert listing_response.status_code == 200
            items = {item["job_url"]: item for item in listing_response.json()["items"]}
            required_item = items[stored_job.job_url]
            assert required_item[C_REQUIRED_LANGUAGES] == ["German", "English"]
            assert items[optional_job.job_url][C_REQUIRED_LANGUAGES] == []
            assert "description" not in required_item
            original_job_id = required_item["id"]
            # Updating only the saved brief proves there is no derived-column backfill.
            statement = update(AvailableJobModel).where(
                AvailableJobModel.id == original_job_id,
            ).values(description=C_REVISED_REQUIREMENT)
            with repository.engine.begin() as connection:
                connection.execute(statement)
            filtered_response = api_client.get("/api/available-jobs", params={
                "preference_id": preference_id, "site": "indeed", "page_size": 1,
            })
            updated_listing = filtered_response.json()
            assert updated_listing["total"] == 1
            assert updated_listing["items"][0][C_REQUIRED_LANGUAGES] == ["Dutch"]
            assert updated_listing["items"][0]["id"] == original_job_id
            stored_job.description = C_OPTIONAL_LANGUAGE
            repository.save_jobs(preference_id, [stored_job])
            refreshed_listing = api_client.get("/api/available-jobs", params={"site": "indeed"}).json()
            assert refreshed_listing["items"][0][C_REQUIRED_LANGUAGES] == []
            assert refreshed_listing["items"][0]["id"] == original_job_id

