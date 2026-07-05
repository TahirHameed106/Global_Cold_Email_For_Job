"""
sources/wellfound.py — Wellfound (formerly AngelList Talent) — DISABLED by default.

Why this is a stub, not a scraper:
  Wellfound is exactly where your target companies (5-10 person startups)
  live, and it shows team size directly — but it requires a logged-in
  session to browse listings, and automated scraping behind a login wall
  violates their Terms of Service and risks your account.

What to do instead (manual, ~10 min/week, zero risk):
  1. Log into Wellfound normally in your browser.
  2. Use their built-in filters: Remote, Company size 1-10, role = Software
     Engineering Intern/Junior.
  3. For roles you like, use Wellfound's own "message" feature to reach the
     founder directly through the platform — this is often BETTER than email
     because founders check it more actively than a cold inbox.
  4. For any listing you want the bot to also track/CV-tailor for, paste the
     job title + description into `manual_job_input()` below, or into
     data/manual_jobs.json (see the template file) and this adapter will
     pick it up and run it through the same matcher/tailor/tracker pipeline.

This keeps Wellfound fully in your control while still using the bot's
matching and CV tailoring for jobs you find there.
"""

import json
import os
from .base import normalize_job

MANUAL_JOBS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "manual_jobs.json")


def fetch_jobs(keywords=None, employment_types=None, max_jobs=25):
    """
    Loads any jobs YOU manually pasted into data/manual_jobs.json.
    Returns an empty list if that file doesn't exist yet — this is expected
    and not an error.
    """
    if not os.path.exists(MANUAL_JOBS_FILE):
        return []

    with open(MANUAL_JOBS_FILE, "r", encoding="utf-8") as f:
        raw_jobs = json.load(f)

    jobs = []
    for j in raw_jobs[:max_jobs]:
        if j.get("_example"):
            continue  # skip the template example entry
        jobs.append(normalize_job(
            source="Wellfound (manual)",
            title=j.get("title", "N/A"),
            company=j.get("company", "Unknown"),
            company_domain=j.get("company_domain", ""),
            company_size=j.get("company_size", "1-10"),
            location=j.get("location", "Remote"),
            remote=True,
            employment_type=j.get("employment_type", "unknown"),
            description=j.get("description", ""),
            job_url=j.get("job_url", ""),
            posted=j.get("posted", ""),
            tags=j.get("tags", []),
        ))
    print(f"[Wellfound-manual] {len(jobs)} manually-added job(s) loaded")
    return jobs
