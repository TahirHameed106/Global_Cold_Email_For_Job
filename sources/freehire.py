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

    NOTE: company_size=1-10 combined with every other filter can return 0
    results — genuinely tiny startups rarely use the ATS platforms freehire
    aggregates from (Greenhouse/Lever/Ashby are usually adopted once a
    company is past pure founder-hiring). If the strict query comes back
    empty, this automatically retries once without the company_size filter
    rather than silently giving up.
    """
    employment_types = employment_types or []

    seniority_values = []
    if any(t in employment_types for t in ["internship"]):
        seniority_values.append("intern")
    if any(t in employment_types for t in ["junior", "entry-level"]):
        seniority_values.append("junior")

    def build_params(include_size):
        params = [("work_mode", "remote"), ("limit", min(max_jobs, 100))]
        for cat in SOFTWARE_CATEGORIES:
            params.append(("category", cat))
        for sen in seniority_values:
            params.append(("seniority", sen))
        if include_size and company_size:
            params.append(("company_size", company_size))
        # No full-text `q` here deliberately — combined with every other
        # filter above, requiring exact keyword-phrase overlap too was
        # over-constraining the query into an empty set. The category +
        # seniority filters already scope this to real software roles;
        # keyword_matches() below does the finer text check client-side.
        return params

    def run_query(params):
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[freehire.dev] Fetch failed: {e}")
            return None

    jobs = []
    data = run_query(build_params(include_size=True))
    total = (data or {}).get("meta", {}).get("total", 0)

    if data is not None and total == 0 and company_size:
        print(f"[freehire.dev] 0 results with company_size={company_size} filter — "
              f"retrying without it (still remote + junior/intern + software categories).")
        data = run_query(build_params(include_size=False))
        total = (data or {}).get("meta", {}).get("total", 0)

    if not data:
        return jobs

    for job_raw in data.get("data", []):
        if len(jobs) >= max_jobs:
            break
        job = _parse_job(job_raw)
        if keyword_matches(f"{job['title']} {job['description']}", keywords):
            jobs.append(job)

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