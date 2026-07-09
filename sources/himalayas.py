"""
sources/himalayas.py — Himalayas.app public jobs API adapter.

Verified against Himalayas' own docs (https://himalayas.app/docs/remote-jobs-api):
  - Correct endpoint is /jobs/api/search (NOT /api/jobs — that was wrong)
  - Free, no API key required
  - Supports server-side keyword + employmentType filtering directly,
    so we don't need to do our own text matching for this source
"""

import requests
from .base import normalize_job

SEARCH_URL = "https://himalayas.app/jobs/api/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}

# Maps our profile.yaml employment_types to Himalayas' documented enum values
EMPLOYMENT_TYPE_MAP = {
    "internship": "Intern",
    "volunteer": "Volunteer",
    "junior": None,       # Himalayas has no "junior" enum — filtered by keyword instead
    "entry-level": None,
}


def _parse_job(job_raw):
    return normalize_job(
        source="Himalayas",
        title=job_raw.get("title", "N/A"),
        company=job_raw.get("companyName", "Unknown"),
        company_domain=job_raw.get("companyWebsite", "") or "",
        company_size=job_raw.get("companySize", "size_unknown") or "size_unknown",
        location=", ".join(job_raw.get("locationRestrictions", []) or []) or "Remote (worldwide)",
        remote=True,
        employment_type=job_raw.get("employmentType", "unknown") or "unknown",
        description=job_raw.get("description", "") or "",
        job_url=job_raw.get("applicationLink", "") or job_raw.get("guid", ""),
        posted=job_raw.get("pubDate", ""),
        tags=job_raw.get("categories", []) or [],
    )


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    """
    Uses Himalayas' own search endpoint, which does server-side keyword and
    employment-type filtering — one request per keyword to cover your list.
    """
    jobs = []
    seen_urls = set()
    employment_types = employment_types or []

    himalayas_types = [EMPLOYMENT_TYPE_MAP.get(t) for t in employment_types]
    himalayas_types = [t for t in himalayas_types if t]  # drop unmapped/None

    for kw in keywords:
        if len(jobs) >= max_jobs:
            break
        params = {"keyword": kw, "limit": min(max_jobs, 20)}
        if himalayas_types:
            params["employmentType"] = ",".join(himalayas_types)

        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Himalayas] Search failed for '{kw}': {e}")
            continue

        raw_list = data.get("jobs", data.get("data", [])) if isinstance(data, dict) else data
        for job_raw in (raw_list or []):
            if len(jobs) >= max_jobs:
                break
            try:
                job = _parse_job(job_raw)
            except Exception:
                continue
            if job["job_url"] in seen_urls:
                continue
            seen_urls.add(job["job_url"])
            jobs.append(job)

    print(f"[Himalayas] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    print("Testing Himalayas search endpoint with keyword 'junior'...")
    try:
        resp = requests.get(SEARCH_URL, params={"keyword": "junior", "limit": 1}, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print("Raw response shape (verify field names against this if parsing breaks):")
        import json
        print(json.dumps(data, indent=2)[:1500])
    except Exception as e:
        print(f"Could not fetch sample job: {e}")
