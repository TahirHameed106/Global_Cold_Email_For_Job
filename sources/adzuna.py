"""
sources/adzuna.py — Adzuna public job search API.
Free tier signup: https://developer.adzuna.com/ (instant, no cost)
Requires ADZUNA_APP_ID and ADZUNA_APP_KEY in your .env

Adzuna aggregates real listings (including many Indeed-sourced postings)
legitimately through a licensed data partnership — this is the legal way
to get Indeed-style coverage without scraping Indeed directly.

Country coverage relevant to your profile: UK, US, Germany, Austria, Australia.
(Adzuna does not cover UAE or Saudi Arabia — use Jooble for those.)
"""

import os
import time
import requests
from .base import normalize_job

BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

# Maps your profile.yaml country names to Adzuna's country codes
COUNTRY_CODES = {
    "United Kingdom": "gb",
    "United States": "us",
    "Germany": "de",
    "Austria": "at",
    "Australia": "au",
}


def _fetch_for_country(country_name, country_code, keywords, app_id, app_key, max_jobs):
    jobs = []
    # BUG FIX: joining multiple keyword phrases into one "what" param makes
    # Adzuna AND-match every single word across all phrases combined — nearly
    # impossible to satisfy. "what_or" instead OR-matches individual words,
    # which is what we actually want at this loose collection stage (the AI
    # matcher in core/matcher.py does the real strict filtering later).
    stopwords = {"the", "and", "for", "with", "a", "an", "of", "in", "at"}
    words = set()
    for kw in keywords:
        words |= {w for w in kw.lower().split() if len(w) > 2 and w not in stopwords}
    query = " ".join(words)

    url = BASE_URL.format(country=country_code, page=1)

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(max_jobs, 50),
        "what_or": query,
        "full_time": 0,
        "sort_by": "date",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Adzuna] Fetch failed for {country_name}: {e}")
        return jobs

    for job_raw in data.get("results", []):
        jobs.append(normalize_job(
            source=f"Adzuna ({country_name})",
            title=job_raw.get("title", "N/A"),
            company=job_raw.get("company", {}).get("display_name", "Unknown"),
            company_domain="",  # Adzuna doesn't expose this — contact_finder derives it
            location=job_raw.get("location", {}).get("display_name", country_name),
            remote="remote" in job_raw.get("title", "").lower() or "remote" in job_raw.get("description", "").lower(),
            employment_type="unknown",
            description=job_raw.get("description", ""),
            job_url=job_raw.get("redirect_url", ""),
            posted=job_raw.get("created", ""),
            tags=[],
        ))
    return jobs


def fetch_jobs(keywords, employment_types=None, max_jobs=25, target_countries=None, **kwargs):
    """
    Fetches jobs across every target country that Adzuna supports.
    target_countries: list of country names from profile.yaml — if None,
    searches all countries Adzuna covers.
    """
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        print("[Adzuna] Skipped — ADZUNA_APP_ID / ADZUNA_APP_KEY not set in .env "
              "(free signup at https://developer.adzuna.com/)")
        return []

    countries_to_search = COUNTRY_CODES
    if target_countries:
        countries_to_search = {
            name: code for name, code in COUNTRY_CODES.items() if name in target_countries
        }

    all_jobs = []
    per_country_limit = max(1, max_jobs // max(len(countries_to_search), 1))

    for name, code in countries_to_search.items():
        country_jobs = _fetch_for_country(name, code, keywords, app_id, app_key, per_country_limit)
        all_jobs.extend(country_jobs)
        time.sleep(0.5)  # be polite between country calls

    print(f"[Adzuna] {len(all_jobs)} job(s) found across {len(countries_to_search)} countries")
    return all_jobs[:max_jobs]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results = fetch_jobs(keywords=["junior", "intern", "software"], max_jobs=10)
    for r in results:
        print(f"- {r['title']} @ {r['company']} ({r['source']}) | {r['job_url']}")
