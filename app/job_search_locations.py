"""Provide offline country and city choices for saved job searches."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from geonamescache import GeonamesCache

C_ROUTER = APIRouter(prefix="/api/job-search-locations", tags=["Job search locations"])
# Use the name accepted by JobSpy while retaining the catalog's stable ISO code.
C_COUNTRY_NAME_OVERRIDES = {"NL": "Netherlands"}


class JobSearchLocationCatalog:
    """Index the bundled GeoNames catalog without network or database access."""

    def __init__(self) -> None:
        """Load country metadata and defer the larger city index until needed."""
        self.source = GeonamesCache()
        self.countries = self.source.get_countries()
        self.cities_by_country: dict[str, list[str]] | None = None

    def list_countries(self) -> list[dict[str, str]]:
        """Return alphabetized names and ISO codes for dropdowns and saved aliases."""
        return sorted(
            [
                {
                    "code": country_code,
                    "name": C_COUNTRY_NAME_OVERRIDES.get(country_code, country["name"]),
                    "iso3": country["iso3"],
                }
                for country_code, country in self.countries.items()
            ],
            key=lambda country: country["name"].casefold(),
        )

    def list_cities(self, country_code: str) -> list[str]:
        """Return distinct city names for one ISO country code, ignoring case."""
        normalized_code = country_code.strip().upper()
        if normalized_code not in self.countries:
            raise HTTPException(404, "Country not found in the location catalog.")
        if self.cities_by_country is None:
            # The saved-search schema stores names, so identical names share a choice.
            city_names: dict[str, set[str]] = {}
            for city in self.source.get_cities().values():
                city_names.setdefault(city["countrycode"], set()).add(city["name"])
            self.cities_by_country = {
                country: sorted(names, key=str.casefold)
                for country, names in city_names.items()
            }
        return self.cities_by_country.get(normalized_code, [])


@lru_cache(maxsize=1)
def get_location_catalog() -> JobSearchLocationCatalog:
    """Reuse a process-local catalog across dropdown requests."""
    return JobSearchLocationCatalog()


@C_ROUTER.get("/countries")
def list_location_countries() -> list[dict[str, str]]:
    """Expose local country choices without changing saved preference values."""
    return get_location_catalog().list_countries()


@C_ROUTER.get("/countries/{country_code}/cities")
def list_location_cities(country_code: str) -> list[str]:
    """Expose the city dropdown choices for the selected country."""
    return get_location_catalog().list_cities(country_code)
