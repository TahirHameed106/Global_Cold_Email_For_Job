"""
sources/freehire.py — freehire.dev public API. Free, NO API KEY NEEDED for
search (only needed for tracking your own applications on their site, which
we don't use). Aggregates directly from company career pages (Greenhouse,
Lever, Ashby, Teamtailor, SuccessFactors) — not reposted listings.

This is the most precisely-filterable source in the pipeline: it has
server-side filters for exactly what matters to your profile —
seniority=intern/junior AND company_size=1-10 — so the "startup team of
5-10 people" requirement is enforced by their API itself, not guessed
afterward like with other sources.

Docs: https://freehire.dev/docs/api
"""

import requests
from .base import normalize_job, keyword_matches

SEARCH_URL = "https://freehire.dev/api/v1/jobs/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}

# Software-relevant categories from their fixed vocabulary (see docs table)
SOFTWARE_CATEGORIES = ["backend", "frontend", "fullstack", "qa", "devops", "mobile"]


def _parse_job(job_raw):
    enrichment = job_raw.get("enrichment", {})
    return normalize_job(
        source="freehire.dev",
        title=job_raw.get("title", "N/A"),
        company=job_raw.get("company", "Unknown"),
        company_domain="",  # freehire gives the ATS posting URL, not the company's own domain
        company_size=job_raw.get("company_size", "size_unknown") or "size_unknown",
        location=job_raw.get("location", "Remote") or "Remote",
        remote=job_raw.get("work_mode") == "remote",
        employment_type=enrichment.get("seniority", "unknown") or "unknown",
        description=job_raw.get("description", "") or job_raw.get("title", ""),
        job_url=job_raw.get("url", ""),
        posted=job_raw.get("posted_at", ""),
        tags=job_raw.get("skills", []) or [],
    )


def fetch_jobs(keywords, employment_types=None, max_jobs=25, company_size=None, **kwargs):
    """
    company_size: e.g. "1-10" — pass through from profile.yaml's
    search.company_size range. If given, freehire filters server-side
    instead of us guessing after the fact.
    """
    jobs = []
    employment_types = employment_types or []

    # Map our profile's employment_types to freehire's seniority vocabulary
    seniority_values = []
    if any(t in employment_types for t in ["internship"]):
        seniority_values.append("intern")
    if any(t in employment_types for t in ["junior", "entry-level"]):
        seniority_values.append("junior")

    params = [
        ("work_mode", "remote"),
        ("limit", min(max_jobs, 100)),
    ]
    for cat in SOFTWARE_CATEGORIES:
        params.append(("category", cat))
    for sen in seniority_values:
        params.append(("seniority", sen))
    if company_size:
        params.append(("company_size", company_size))
    if keywords:
        params.append(("q", keywords[0]))  # their full-text search — one focused term works best

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[freehire.dev] Fetch failed: {e}")
        return jobs

    for job_raw in data.get("data", []):
        if len(jobs) >= max_jobs:
            break
        job = _parse_job(job_raw)
        # Extra client-side keyword check in case the q= search was too broad
        if keyword_matches(f"{job['title']} {job['description']}", keywords):
            jobs.append(job)

    total = data.get("meta", {}).get("total", len(jobs))
    print(f"[freehire.dev] {len(jobs)} matching job(s) found ({total} total match the server-side filters)")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(
        keywords=["junior", "intern", "software"],
        employment_types=["internship", "junior"],
        company_size="1-10",
        max_jobs=10,
    )
    for r in results:
        print(f"- {r['title']} @ {r['company']} ({r['company_size']}) | {r['job_url']}")
