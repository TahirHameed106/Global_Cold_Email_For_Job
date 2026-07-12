"""
sources/arbeitnow.py — Arbeitnow public API. Free, no signup, no API key.
https://www.arbeitnow.com/api/job-board-api
Strong DACH (Germany/Austria/Switzerland) coverage — useful for your targets.
"""

import requests
from .base import normalize_job, keyword_matches

API_URL = "https://www.arbeitnow.com/api/job-board-api"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    jobs = []
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Arbeitnow] Fetch failed: {e}")
        return jobs

    for job_raw in data.get("data", []):
        if len(jobs) >= max_jobs:
            break
        text = f"{job_raw.get('title','')} {job_raw.get('description','')}"
        if not keyword_matches(text, keywords):
            continue
        jobs.append(normalize_job(
            source="Arbeitnow",
            title=job_raw.get("title", "N/A"),
            company=job_raw.get("company_name", "Unknown"),
            company_domain="",
            location=job_raw.get("location", "Remote") or "Remote",
            remote=job_raw.get("remote", False),
            employment_type=", ".join(job_raw.get("job_types", [])) or "unknown",
            description=job_raw.get("description", ""),
            job_url=job_raw.get("url", ""),
            posted=str(job_raw.get("created_at", "")),
            tags=job_raw.get("tags", []),
        ))

    print(f"[Arbeitnow] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(keywords=["junior", "intern", "software"], max_jobs=5)
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
