"""
sources/linkedin.py — LinkedIn — DISABLED for automation, manual-assist only.

Why this isn't a scraper:
  LinkedIn has no public jobs-search API for regular developers (their
  official API is enterprise/partner-only), and their Terms of Service
  explicitly prohibit automated scraping — they actively detect and block
  it, and have pursued legal action against scraping tools before. This
  isn't a gray area worth risking your account or facing legal exposure over.

What to do instead (a few minutes a day, zero risk):
  1. Browse LinkedIn Jobs normally with their built-in filters (Remote,
     Internship/Entry level, and search your target keywords)
  2. For roles that look like a real fit, paste the job details into
     data/manual_jobs_linkedin.json (see the template)
  3. This adapter picks them up and runs them through the exact same
     matcher/tailor/contact/send/track pipeline as every automated source

Bonus: LinkedIn also shows you the poster's name and title directly on the
listing — if they've listed a public email in their profile "Contact info"
(something they chose to share), that's fair to note manually in the job's
"notes" field for contact_finder to try, without any bot touching LinkedIn.
"""

import json
import os
from .base import normalize_job

MANUAL_JOBS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "manual_jobs_linkedin.json")


def fetch_jobs(keywords=None, employment_types=None, max_jobs=25, **kwargs):
    """
    Loads jobs YOU manually pasted into data/manual_jobs_linkedin.json.
    Returns an empty list if that file doesn't exist yet — expected, not an error.
    """
    if not os.path.exists(MANUAL_JOBS_FILE):
        return []

    with open(MANUAL_JOBS_FILE, "r", encoding="utf-8") as f:
        raw_jobs = json.load(f)

    jobs = []
    for j in raw_jobs[:max_jobs]:
        if j.get("_example"):
            continue
        jobs.append(normalize_job(
            source="LinkedIn (manual)",
            title=j.get("title", "N/A"),
            company=j.get("company", "Unknown"),
            company_domain=j.get("company_domain", ""),
            company_size=j.get("company_size", "size_unknown"),
            location=j.get("location", "Remote"),
            remote=True,
            employment_type=j.get("employment_type", "unknown"),
            description=j.get("description", ""),
            job_url=j.get("job_url", ""),
            posted=j.get("posted", ""),
            tags=j.get("tags", []),
        ))
    print(f"[LinkedIn-manual] {len(jobs)} manually-added job(s) loaded")
    return jobs
