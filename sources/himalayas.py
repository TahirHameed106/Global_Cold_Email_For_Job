"""
sources/himalayas.py — Himalayas.app public jobs API adapter.

IMPORTANT: Public APIs change their response shape over time, and I could
not verify this endpoint's exact current field names from this environment
(no live internet access during code generation). Run this file directly
first:

    python -m sources.himalayas

It will print the raw shape of the first job returned so you can confirm
the field names below still match. If they don't, adjust the .get() keys
in `_parse_job()` — everything else in the pipeline stays the same.
"""

import time
import requests
from .base import normalize_job

API_URL = "https://himalayas.app/api/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def _parse_job(job_raw):
    """Map Himalayas' raw job object to our normalized schema. Adjust keys if needed."""
    company = job_raw.get("companyName") or job_raw.get("company", {}).get("name", "Unknown")
    return normalize_job(
        source="Himalayas",
        title=job_raw.get("title", "N/A"),
        company=company,
        company_domain=job_raw.get("companyWebsite", "") or "",
        company_size=job_raw.get("companySize", "size_unknown") or "size_unknown",
        location=job_raw.get("locationRestrictions", ["Remote"])[0] if job_raw.get("locationRestrictions") else "Remote",
        remote=True,
        employment_type=job_raw.get("employmentType", "unknown") or "unknown",
        description=job_raw.get("description", "") or job_raw.get("excerpt", ""),
        job_url=job_raw.get("applicationLink", "") or job_raw.get("url", ""),
        posted=job_raw.get("publishedAt", ""),
        tags=job_raw.get("categories", []) or [],
    )


def _looks_like_target(job, keywords):
    text = f"{job['title']} {job['description']}".lower()
    return any(kw.lower() in text for kw in keywords)


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    """Return a list of normalized job dicts matching any of the given keywords."""
    jobs = []
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Himalayas] Fetch failed: {e}")
        return jobs

    # Defensive: the job list might be at data["jobs"], data["data"], or the root list itself.
    raw_jobs = data.get("jobs") if isinstance(data, dict) else data
    if raw_jobs is None and isinstance(data, dict):
        raw_jobs = data.get("data", [])
    raw_jobs = raw_jobs or []

    for job_raw in raw_jobs:
        if len(jobs) >= max_jobs:
            break
        try:
            job = _parse_job(job_raw)
        except Exception:
            continue
        if _looks_like_target(job, keywords):
            jobs.append(job)
        time.sleep(0.1)

    print(f"[Himalayas] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        data = resp.json()
        raw_jobs = data.get("jobs", data) if isinstance(data, dict) else data
        print("Raw shape of first job (verify field names against this):")
        import json
        print(json.dumps(raw_jobs[0], indent=2)[:1500])
    except Exception as e:
        print(f"Could not fetch sample job: {e}")
