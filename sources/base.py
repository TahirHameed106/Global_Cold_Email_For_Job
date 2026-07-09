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


_STOPWORDS = {"the", "and", "for", "with", "using", "via", "a", "an", "of", "in", "at", "to"}


def keyword_matches(text, keywords, min_hits=1):
    """
    Loose, word-level keyword match — replaces fragile exact-phrase matching.

    A keyword like "software engineer intern" almost never appears verbatim
    in a real job posting, even when the posting is a perfect match (it might
    say "Junior Software Engineer (Internship)" instead). This checks
    individual significant words from each keyword phrase instead, so any
    real overlap counts as a hit.

    This is intentionally loose at this stage — the AI match scorer
    (core/matcher.py) does the real, strict filtering later. This stage's
    only job is to not throw away good jobs before they even get scored.
    """
    text_lower = text.lower()
    for kw in keywords:
        words = [w for w in kw.lower().split() if len(w) > 2 and w not in _STOPWORDS]
        hits = sum(1 for w in words if w in text_lower)
        if hits >= min_hits:
            return True
    return False
