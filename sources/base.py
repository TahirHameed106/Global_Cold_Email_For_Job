"""
base.py — Every source adapter returns jobs in this exact shape, so the
rest of the pipeline (matcher, tailor, sender) never needs to know or care
which site a job came from.
"""

JOB_SCHEMA_EXAMPLE = {
    "source": "RemoteOK",
    "title": "Junior Backend Developer",
    "company": "Acme Startup",
    "company_domain": "acmestartup.com",   # used later by contact_finder.py
    "company_size": "size_unknown",         # "1-10", "11-50", etc. or "size_unknown"
    "location": "Remote",
    "remote": True,
    "employment_type": "full-time",         # best guess: internship/junior/full-time/volunteer
    "description": "Full job description text...",
    "job_url": "https://...",
    "posted": "2026-07-01",
    "tags": ["python", "django"],
}


def normalize_job(**kwargs):
    """Fill in a job dict with sensible defaults for any missing fields."""
    job = dict(JOB_SCHEMA_EXAMPLE)
    job.update(kwargs)
    return job
