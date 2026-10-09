"""JobSpy searches with independent board failures and paginated local results."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import json
import logging
import math
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query

from .database import connect
from .job_search_preferences import get_preference
from .models import JobBoard, JobSearchInput
from .request_logging import TRACE

router = APIRouter(prefix="/api", tags=["Job search"])
logger = logging.getLogger(__name__)


def scrape_jobs(**kwargs):
    # Lazy loading keeps the rest of ApplyKit usable if dependencies need installing.
    from jobspy import scrape_jobs as scrape

    return scrape(**kwargs)


def _country(value: str):
    from jobspy.model import Country

    if not value:
        return None
    try:
        return Country.from_string(value)
    except ValueError:
        # Accept common ISO codes as well as JobSpy's country names.
        for country in Country:
            if value.lower() in country.value[1].split(":"):
                return country
    return None


def _board_arguments(preference: dict, site: str, results_wanted: int) -> dict:
    country = _country(preference["country"])
    if site in {"indeed", "glassdoor"} and (country is None or country.name == "WORLDWIDE"):
        raise ValueError("Set a supported country in this saved search for Indeed and Glassdoor.")
    if site == "glassdoor":
        try:
            country.glassdoor_domain_value
        except Exception as exc:
            raise ValueError("Glassdoor does not support this search's country.") from exc
    if site == "zip_recruiter" and country and country.name not in {"USA", "CANADA"}:
        raise ValueError("ZipRecruiter supports searches in the US and Canada.")
    if site == "naukri" and country and country.name != "INDIA":
        raise ValueError("Naukri supports searches in India.")
    if site == "bdjobs" and country and country.name != "BANGLADESH":
        raise ValueError("BDJobs supports searches in Bangladesh.")
    args = {
        "site_name": [site],
        "search_term": preference["job_title"],
        "location": ", ".join(filter(None, [preference["city"], preference["country"]])) or None,
        "results_wanted": results_wanted,
        "distance": math.ceil(preference["radius_km"] / 1.609344),
        "hours_old": preference["posted_within_days"] * 24 if preference["posted_within_days"] else None,
        "fetch_description": True,
        "description_format": "plain",
        "verbose": 0,
    }
    if country:
        args["country_indeed"] = country.value[0].split(",")[0]
    return args


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _records(frame, site: str, keywords: list[str]) -> tuple[list[dict], int]:
    # Pandas JSON converts NaN/NaT to null and numpy scalars to JSON primitives.
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    jobs, skipped = [], 0
    for record in records:
        title, url = _text(record.get("title")), _text(record.get("job_url"))
        try:
            parsed = urlsplit(url)
            valid_url = parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid_url = False
        if not title or not valid_url:
            skipped += 1
            continue
        description = _text(record.get("description"))
        if not all(word.casefold() in description.casefold() for word in keywords):
            continue
        posted = record.get("date_posted")
        jobs.append({
            "site": site, "job_url": url, "job_title": title,
            "company": _text(record.get("company")),
            "location": _text(record.get("location")), "description": description,
            "date_posted": _text(posted)[:10] if posted else None,
            "job_type": _text(record.get("job_type")),
            "is_remote": None if record.get("is_remote") is None else int(bool(record["is_remote"])),
            "raw_data": json.dumps(record, ensure_ascii=False, allow_nan=False),
        })
    return jobs, skipped


def _scrape_board(preference: dict, site: str, results_wanted: int):
    args = _board_arguments(preference, site, results_wanted)
    return _records(scrape_jobs(**args), site, preference["keywords"])


@router.post("/job-search")
def search_jobs(payload: JobSearchInput):
    preference = get_preference(payload.preference_id)
    logger.info(
        "job_search_started preference_id=%s sites=%s results_wanted=%d preference=%s",
        payload.preference_id, json.dumps(payload.sites), payload.results_wanted,
        json.dumps(preference, ensure_ascii=False),
    )
    jobs, boards, warnings = [], {}, []
    with ThreadPoolExecutor(max_workers=len(payload.sites)) as executor:
        futures = {
            executor.submit(_scrape_board, preference, site, payload.results_wanted): site
            for site in payload.sites
        }
        for future in as_completed(futures):
            site = futures[future]
            try:
                found, skipped = future.result()
                jobs.extend(found)
                boards[site] = {"status": "completed", "count": len(found)}
                logger.info(
                    "job_search_board_completed preference_id=%s site=%s count=%d skipped=%d",
                    payload.preference_id, site, len(found), skipped,
                )
                if logger.isEnabledFor(TRACE):
                    for job in found:
                        logger.log(
                            TRACE, "job_search_result preference_id=%s site=%s job=%s",
                            payload.preference_id, site, json.dumps(job, ensure_ascii=False),
                        )
                if skipped:
                    warnings.append(f"{site}: skipped {skipped} incomplete postings.")
            except ValueError as exc:
                logger.warning(
                    "job_search_board_failed preference_id=%s site=%s error=%s",
                    payload.preference_id, site, exc,
                )
                boards[site] = {"status": "failed", "count": 0}
                warnings.append(f"{site}: {exc}")
            except Exception:
                logger.exception(
                    "job_search_board_failed preference_id=%s site=%s",
                    payload.preference_id, site,
                )
                boards[site] = {"status": "failed", "count": 0}
                warnings.append(f"{site}: the search failed. Try again later or check your connection.")
    if all(board["status"] == "failed" for board in boards.values()):
        logger.error("job_search_failed preference_id=%s reason=all_boards_failed", payload.preference_id)
        raise HTTPException(502, {"message": "All job board searches failed. Previously fetched jobs are still available.", "warnings": warnings})
    with closing(connect()) as db, db:
        # The user may delete the preference while network requests are running.
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM job_search_preferences WHERE id = ?", (payload.preference_id,)).fetchone():
            raise HTTPException(409, "The saved search was deleted while fetching jobs.")
        for job in jobs:
            db.execute(
                """INSERT INTO available_jobs
                   (site, job_url, job_title, company, location, description, date_posted, job_type, is_remote, raw_data)
                   VALUES (:site, :job_url, :job_title, :company, :location, :description, :date_posted, :job_type, :is_remote, :raw_data)
                   ON CONFLICT(site, job_url) DO UPDATE SET
                   job_title=excluded.job_title, company=excluded.company, location=excluded.location,
                   description=excluded.description, date_posted=excluded.date_posted,
                   job_type=excluded.job_type, is_remote=excluded.is_remote,
                   raw_data=excluded.raw_data, fetched_at=CURRENT_TIMESTAMP""", job,
            )
            db.execute(
                """INSERT OR IGNORE INTO job_search_results(preference_id, job_id)
                   SELECT ?, id FROM available_jobs WHERE site = ? AND job_url = ?""",
                (payload.preference_id, job["site"], job["job_url"]),
            )
    result = {
        "preference_id": payload.preference_id,
        "fetched": len({(job["site"], job["job_url"]) for job in jobs}),
        "boards": boards, "warnings": sorted(warnings),
    }
    logger.info(
        "job_search_completed preference_id=%s fetched=%d boards=%s warnings=%s",
        payload.preference_id, result["fetched"], json.dumps(boards), json.dumps(result["warnings"]),
    )
    return result


@router.get("/available-jobs")
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    preference_id: int | None = Query(default=None, gt=0),
    site: JobBoard | None = None,
    search: str = Query(default="", max_length=250),
):
    where, params = [], []
    if preference_id is not None:
        where.append("EXISTS (SELECT 1 FROM job_search_results r WHERE r.job_id = j.id AND r.preference_id = ?)")
        params.append(preference_id)
    if site:
        where.append("j.site = ?")
        params.append(site)
    if search.strip():
        where.append("(j.company LIKE ? OR j.job_title LIKE ? OR j.description LIKE ?)")
        params.extend([f"%{search.strip()}%"] * 3)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with closing(connect()) as db, db:
        db.execute("BEGIN")
        if preference_id is not None and not db.execute("SELECT 1 FROM job_search_preferences WHERE id = ?", (preference_id,)).fetchone():
            raise HTTPException(404, "Job search preference not found.")
        total = db.execute(f"SELECT COUNT(*) FROM available_jobs j {clause}", params).fetchone()[0]
        pages = max(1, math.ceil(total / page_size))
        page = min(page, pages)
        rows = db.execute(
            f"""SELECT j.id, j.site, j.job_url, j.job_title, j.company, j.location,
                       j.date_posted, j.job_type, j.is_remote, j.first_fetched_at, j.fetched_at,
                       EXISTS(SELECT 1 FROM applications a WHERE a.source_url = j.job_url
                              AND a.status IN ('Applied', 'Interview', 'Offer')) AS applied
                FROM available_jobs j {clause}
                ORDER BY j.fetched_at DESC, j.id DESC LIMIT ? OFFSET ?""",
            [*params, page_size, (page - 1) * page_size],
        )
        items = [dict(row) for row in rows]
    for item in items:
        item["applied"] = bool(item["applied"])
        if item["is_remote"] is not None:
            item["is_remote"] = bool(item["is_remote"])
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": pages, "has_previous": page > 1, "has_next": page < pages}
