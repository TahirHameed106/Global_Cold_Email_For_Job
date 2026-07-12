"""
sources/jobicy.py — Jobicy public API. Free, no signup, no API key.
https://jobicy.com/api/v2/remote-jobs
"""

import requests
from .base import normalize_job, keyword_matches

API_URL = "https://jobicy.com/api/v2/remote-jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    jobs = []
    params = {"count": min(max_jobs, 50), "tag": "engineering"}

    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Jobicy] Fetch failed: {e}")
        return jobs

    for job_raw in data.get("jobs", []):
        if len(jobs) >= max_jobs:
            break
        text = f"{job_raw.get('jobTitle','')} {job_raw.get('jobExcerpt','') or job_raw.get('jobDescription','')}"
        if not keyword_matches(text, keywords):
            continue
        jobs.append(normalize_job(
            source="Jobicy",
            title=job_raw.get("jobTitle", "N/A"),
            company=job_raw.get("companyName", "Unknown"),
            company_domain="",
            location=job_raw.get("jobGeo", "Remote") or "Remote",
            remote=True,
            employment_type=job_raw.get("jobType", "unknown") or "unknown",
            description=job_raw.get("jobExcerpt", "") or job_raw.get("jobDescription", ""),
            job_url=job_raw.get("url", ""),
            posted=job_raw.get("pubDate", ""),
            tags=job_raw.get("jobIndustry", []) or [],
        ))

    print(f"[Jobicy] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(keywords=["junior", "intern", "software"], max_jobs=5)
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
