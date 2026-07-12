"""
sources/remotive.py — Remotive public API. Free, no signup, no API key.
https://remotive.com/api/remote-jobs
"""

import requests
from .base import normalize_job, keyword_matches

API_URL = "https://remotive.com/api/remote-jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    jobs = []
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Remotive] Fetch failed: {e}")
        return jobs

    for job_raw in data.get("jobs", []):
        if len(jobs) >= max_jobs:
            break
        text = f"{job_raw.get('title','')} {job_raw.get('description','')}"
        if not keyword_matches(text, keywords):
            continue
        jobs.append(normalize_job(
            source="Remotive",
            title=job_raw.get("title", "N/A"),
            company=job_raw.get("company_name", "Unknown"),
            company_domain="",
            location=job_raw.get("candidate_required_location", "Remote") or "Remote",
            remote=True,
            employment_type=job_raw.get("job_type", "unknown") or "unknown",
            description=job_raw.get("description", ""),
            job_url=job_raw.get("url", ""),
            posted=job_raw.get("publication_date", ""),
            tags=job_raw.get("tags", []),
        ))

    print(f"[Remotive] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(keywords=["junior", "intern", "software"], max_jobs=5)
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
