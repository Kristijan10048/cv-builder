"""Verify offline location choices and compatibility with saved search values."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app import database
from app.job_search_adapter import JobSearchAdapter

C_LOCATION_ENDPOINT = "/api/job-search-locations"
C_PREFERENCE_ENDPOINT = "/api/job-search-preferences"


class JobSearchLocationTests(unittest.TestCase):
    """Exercise the catalog through the API using the isolated test database."""

    def setUp(self) -> None:
        """Start application lifecycle hooks using the test database fixture."""
        temporary_directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(database, "DB_PATH", Path(temporary_directory) / "locations.db"))
        self.client = self.enterContext(TestClient(app))

    def test_country_choices_are_sorted_and_have_iso_identifiers(self) -> None:
        """Offer worldwide country choices with stable identifiers and names."""
        response = self.client.get(f"{C_LOCATION_ENDPOINT}/countries")
        self.assertEqual(response.status_code, 200)
        countries = response.json()
        self.assertGreater(len(countries), 200)
        self.assertEqual(countries, sorted(countries, key=lambda country: country["name"].casefold()))
        self.assertIn({"code": "DE", "name": "Germany", "iso3": "DEU"}, countries)
        self.assertEqual(len({country["code"] for country in countries}), len(countries))

    def test_city_choices_are_country_specific_sorted_and_repeatable(self) -> None:
        """Keep city choices scoped to one country across repeated requests."""
        german_cities = self.client.get(f"{C_LOCATION_ENDPOINT}/countries/DE/cities").json()
        british_cities = self.client.get(f"{C_LOCATION_ENDPOINT}/countries/GB/cities").json()
        self.assertIn("Duisburg", german_cities)
        self.assertIn("Berlin", german_cities)
        self.assertIn("London", british_cities)
        self.assertNotIn("Duisburg", british_cities)
        self.assertEqual(german_cities, sorted(set(german_cities), key=str.casefold))
        self.assertEqual(
            german_cities,
            self.client.get(f"{C_LOCATION_ENDPOINT}/countries/de/cities").json(),
        )

    def test_unknown_country_has_readable_error(self) -> None:
        """Reject invalid country codes instead of serving a worldwide city list."""
        response = self.client.get(f"{C_LOCATION_ENDPOINT}/countries/ZZ/cities")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Country not found", response.json()["detail"])

    def test_dropdown_country_names_work_with_existing_job_search(self) -> None:
        """Keep common supported countries usable after selecting their display name."""
        countries = self.client.get(f"{C_LOCATION_ENDPOINT}/countries").json()
        for country in countries:
            if country["code"] in {"DE", "GB", "US", "NL", "SI", "CZ"}:
                with self.subTest(country=country["name"]):
                    self.assertIsNotNone(JobSearchAdapter.resolve_country(country["name"]))

    def test_catalog_requests_preserve_custom_and_countryless_preferences(self) -> None:
        """Retain existing free-text locations while exposing dropdown choices."""
        for country_value in ("", "DE", "A saved country outside the catalog"):
            with self.subTest(country=country_value):
                saved_response = self.client.post(C_PREFERENCE_ENDPOINT, json={
                    "job_title": "Developer",
                    "country": country_value,
                    "city": "A small village",
                    "radius_km": 25,
                })
                self.assertEqual(saved_response.status_code, 201)
                saved_preference = saved_response.json()
                self.client.get(f"{C_LOCATION_ENDPOINT}/countries")
                self.client.get(f"{C_LOCATION_ENDPOINT}/countries/DE/cities")
                response = self.client.get(f"{C_PREFERENCE_ENDPOINT}/{saved_preference['id']}")
                self.assertEqual(response.json(), saved_preference)
