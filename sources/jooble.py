"""
sources/jooble.py — Jooble public job search API.
Free API key signup: https://jooble.org/api/about (instant, no cost)
Requires JOOBLE_API_KEY in your .env

Jooble aggregates listings from many boards internationally and has better
Middle East coverage than Adzuna — useful for your UAE / Saudi Arabia targets.
"""

import os
import time
import requests
from .base import normalize_job

# Jooble's location strings work best as plain country/city names, not codes.
DEFAULT_LOCATIONS = ["United Arab Emirates", "Saudi Arabia", "Remote"]


def _fetch_for_location(location, keywords, api_key, max_jobs):
    jobs = []
    url = f"https://jooble.org/api/{api_key}"
    payload = {
        "keywords": " ".join(keywords[:3]),
        "location": location,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Jooble] Fetch failed for {location}: {e}")
        return jobs

    for job_raw in data.get("jobs", [])[:max_jobs]:
        jobs.append(normalize_job(
            source=f"Jooble ({location})",
            title=job_raw.get("title", "N/A"),
            company=job_raw.get("company", "Unknown"),
            company_domain="",
            location=job_raw.get("location", location),
            remote="remote" in job_raw.get("title", "").lower() or "remote" in job_raw.get("snippet", "").lower(),
            employment_type=job_raw.get("type", "unknown") or "unknown",
            description=job_raw.get("snippet", ""),
            job_url=job_raw.get("link", ""),
            posted=job_raw.get("updated", ""),
            tags=[],
        ))
    return jobs


def fetch_jobs(keywords, employment_types=None, max_jobs=25, locations=None, **kwargs):
    """
    Fetches jobs across the given locations (defaults to UAE, Saudi Arabia,
    and Remote — the ones Adzuna doesn't cover for you).
    """
    api_key = os.getenv("JOOBLE_API_KEY")
    if not api_key:
        print("[Jooble] Skipped — JOOBLE_API_KEY not set in .env "
              "(free signup at https://jooble.org/api/about)")
        return []

    locations_to_search = locations or DEFAULT_LOCATIONS
    all_jobs = []
    per_location_limit = max(1, max_jobs // max(len(locations_to_search), 1))

    for loc in locations_to_search:
        loc_jobs = _fetch_for_location(loc, keywords, api_key, per_location_limit)
        all_jobs.extend(loc_jobs)
        time.sleep(0.5)

    print(f"[Jooble] {len(all_jobs)} job(s) found across {len(locations_to_search)} location(s)")
    return all_jobs[:max_jobs]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results = fetch_jobs(keywords=["junior", "software", "intern"], max_jobs=10)
    for r in results:
        print(f"- {r['title']} @ {r['company']} ({r['source']}) | {r['job_url']}")
