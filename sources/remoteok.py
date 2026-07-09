"""
sources/remoteok.py — RemoteOK public API adapter.
No login, no key needed. https://remoteok.com/api returns a JSON array.

NOTE: Public APIs occasionally change their field names. This code reads
fields defensively with .get() and sensible fallbacks, but if RemoteOK
changes their response shape, run this file directly (`python remoteok.py`)
to print one raw job and check the field names still match.
"""

import requests
import time
from .base import normalize_job, keyword_matches

API_URL = "https://remoteok.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def _looks_like_target(job_raw, keywords, employment_types):
    text = f"{job_raw.get('position','')} {job_raw.get('description','')} {' '.join(job_raw.get('tags', []))}"
    return keyword_matches(text, keywords)


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    """Return a list of normalized job dicts matching any of the given keywords."""
    jobs = []
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw_jobs = resp.json()
    except Exception as e:
        print(f"[RemoteOK] Fetch failed: {e}")
        return jobs

    # RemoteOK's first array item is a legal/notice object, not a job — skip it.
    raw_jobs = [j for j in raw_jobs if isinstance(j, dict) and j.get("position")]

    for job_raw in raw_jobs:
        if len(jobs) >= max_jobs:
            break
        if not _looks_like_target(job_raw, keywords, employment_types):
            continue

        company = job_raw.get("company", "Unknown")
        job_url = job_raw.get("url") or job_raw.get("apply_url") or ""
        domain = ""
        if job_raw.get("company_logo"):
            # crude domain guess from company name; contact_finder will verify/refine
            domain = company.lower().replace(" ", "").replace(",", "") + ".com"

        jobs.append(normalize_job(
            source="RemoteOK",
            title=job_raw.get("position", "N/A"),
            company=company,
            company_domain=domain,
            location=job_raw.get("location", "Remote") or "Remote",
            remote=True,
            employment_type="unknown",   # RemoteOK doesn't reliably tag this — matcher/JD text will hint at it
            description=job_raw.get("description", ""),
            job_url=job_url,
            posted=job_raw.get("date", ""),
            tags=job_raw.get("tags", []),
        ))
        time.sleep(0.2)

    print(f"[RemoteOK] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(keywords=["junior", "intern", "entry"], max_jobs=5)
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
