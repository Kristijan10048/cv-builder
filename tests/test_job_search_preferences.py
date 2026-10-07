"""Verify saved searches, validation, the limit, and schema upgrades in isolated DBs."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.db_migrations import MIGRATIONS, run_migrations
from app.main import app


ENDPOINT = "/api/job-search-preferences"


class JobSearchPreferencesTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.db_path = Path(directory) / "preferences.db"
        self.enterContext(patch.object(database, "DB_PATH", self.db_path))
        self.client = self.enterContext(TestClient(app))

    def create(self, **fields):
        response = self.client.post(ENDPOINT, json={"job_title": "Software Developer", **fields})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_preferences_are_normalized_and_persist_after_restart(self):
        saved = self.create(
            job_title=" Software Developer ", country=" Germany ", city=" Duisburg ",
            radius_km=50, keywords=[" Python ", "SQL", "Kundenbetreuung"], posted_within_days=14,
        )
        expected = {
            "job_title": "Software Developer", "country": "Germany", "city": "Duisburg",
            "radius_km": 50, "keywords": ["Python", "SQL", "Kundenbetreuung"], "posted_within_days": 14,
        }
        for field, value in expected.items():
            self.assertEqual(saved[field], value)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(json.loads(db.execute("SELECT keywords FROM job_search_preferences").fetchone()[0]), expected["keywords"])
        with TestClient(app) as restarted:
            self.assertEqual(restarted.get(ENDPOINT).json(), [saved])
            self.assertEqual(restarted.get(f"{ENDPOINT}/{saved['id']}").json(), saved)

    def test_update_and_delete(self):
        saved = self.create(city="Berlin", radius_km=25, keywords=["Python"], posted_within_days=7)
        url = f"{ENDPOINT}/{saved['id']}"
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("UPDATE job_search_preferences SET updated_at = '2000-01-01 00:00:00'")
        updated = self.client.put(url, json={"job_title": "Second Level Support"})
        self.assertEqual(updated.status_code, 200)
        record = updated.json()
        self.assertEqual(record["id"], saved["id"])
        self.assertEqual(record["created_at"], saved["created_at"])
        self.assertNotEqual(record["updated_at"], "2000-01-01 00:00:00")
        self.assertEqual(record["job_title"], "Second Level Support")
        self.assertEqual(record["city"], "")
        self.assertEqual(record["radius_km"], 0)
        self.assertEqual(record["keywords"], [])
        self.assertIsNone(record["posted_within_days"])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(ENDPOINT).json(), [])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(url, json={"job_title": "Missing"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_limit_allows_editing_and_replacement_after_deletion(self):
        saved = [self.create(job_title=f"Role {index}") for index in range(10)]
        rejected = self.client.post(ENDPOINT, json={"job_title": "Eleventh role"})
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("10", rejected.json()["detail"])
        self.assertEqual(len(self.client.get(ENDPOINT).json()), 10)
        url = f"{ENDPOINT}/{saved[0]['id']}"
        self.assertEqual(self.client.put(url, json={"job_title": "Edited at limit"}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.create(job_title="Replacement")
        self.assertEqual(len(self.client.get(ENDPOINT).json()), 10)

    def test_concurrent_creates_cannot_exceed_ten(self):
        for index in range(9):
            self.create(job_title=f"Existing role {index}")
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(
                lambda index: self.client.post(ENDPOINT, json={"job_title": f"Concurrent {index}"}),
                range(4),
            ))
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409, 409, 409])
        self.assertEqual(len(self.client.get(ENDPOINT).json()), 10)

    def test_invalid_inputs_are_rejected_without_saving(self):
        invalid = [
            {"job_title": ""}, {"job_title": "   "}, {"job_title": "x" * 251},
            {"country": "x" * 121}, {"city": "x" * 121},
            {"radius_km": -1}, {"radius_km": 1001}, {"radius_km": 2.5}, {"radius_km": True},
            {"radius_km": 10, "city": "   "},
            {"posted_within_days": 0}, {"posted_within_days": -7}, {"posted_within_days": 3651},
            {"posted_within_days": 1.5}, {"keywords": ["   "]},
            {"keywords": ["x" * 121]}, {"keywords": ["Python"] * 31}, {"keywords": "Python"},
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                response = self.client.post(ENDPOINT, json={"job_title": "Developer", **fields})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(ENDPOINT).json(), [])
        saved = self.create()
        self.assertEqual(self.client.put(f"{ENDPOINT}/{saved['id']}", json={"job_title": " "}).status_code, 422)
        self.assertEqual(self.client.get(f"{ENDPOINT}/{saved['id']}").json(), saved)

    def test_all_posting_age_presets_and_optional_locations(self):
        for days in (None, 1, 3, 7, 14, 30, 90, 365):
            saved = self.create(country="Germany", posted_within_days=days)
            self.assertEqual(saved["posted_within_days"], days)
            self.assertEqual(saved["city"], "")
            self.assertEqual(saved["radius_km"], 0)


class JobSearchPreferenceMigrationTests(unittest.TestCase):
    def database(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return db

    def test_fresh_migration_is_repeatable_and_retains_saved_preferences(self):
        db = self.database()
        run_migrations(db)
        db.execute("INSERT INTO job_search_preferences(job_title) VALUES ('Developer')")
        db.commit()
        run_migrations(db)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], len(MIGRATIONS))
        saved = db.execute("SELECT * FROM job_search_preferences").fetchone()
        self.assertEqual(saved["job_title"], "Developer")
        self.assertEqual(saved["keywords"], "[]")
        self.assertIsNone(saved["posted_within_days"])

    def test_upgrade_from_previous_schema_preserves_existing_data(self):
        db = self.database()
        db.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for migration in MIGRATIONS[:2]:
            migration.apply(db)
            db.execute("INSERT INTO schema_migrations(version, name) VALUES (?, ?)", (migration.version, migration.name))
        db.execute("UPDATE settings SET value = 'saved-model' WHERE key = 'lm_studio_model'")
        db.execute("INSERT INTO applications(company, job_title) VALUES ('Original Company', 'Original Role')")
        db.execute("UPDATE document_templates SET content = 'Original CV' WHERE kind = 'cv'")
        db.commit()
        run_migrations(db)
        self.assertEqual(db.execute("SELECT value FROM settings WHERE key = 'lm_studio_model'").fetchone()[0], "saved-model")
        self.assertEqual(db.execute("SELECT job_title FROM applications").fetchone()[0], "Original Role")
        self.assertEqual(db.execute("SELECT content FROM document_templates WHERE kind = 'cv'").fetchone()[0], "Original CV")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM job_search_preferences").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT name FROM schema_migrations WHERE version = 3").fetchone()[0], "job_search_preferences")


if __name__ == "__main__":
    unittest.main()
