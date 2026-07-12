"""
base.py — Every source adapter returns jobs in this exact shape, so the
rest of the pipeline (matcher, tailor, sender) never needs to know or care
which site a job came from.
"""

import re

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
    "contact_email": "",  # if a human manually found/verified this, skip all guessing
}


def normalize_job(**kwargs):
    """Fill in a job dict with sensible defaults for any missing fields."""
    job = dict(JOB_SCHEMA_EXAMPLE)
    job.update(kwargs)
    return job


_STOPWORDS = {"the", "and", "for", "with", "using", "via", "a", "an", "of", "in", "at", "to"}


def keyword_matches(text, keywords, min_hits=2):
    """
    Loose, word-level keyword match — replaces fragile exact-phrase matching.

    A keyword like "software engineer intern" almost never appears verbatim
    in a real job posting, even when the posting is a perfect match (it might
    say "Junior Software Engineer (Internship)" instead). This checks
    individual significant words from each keyword phrase instead, so any
    real overlap counts as a hit.

    min_hits=2 requires at least 2 distinct meaningful words to overlap
    (e.g. both "developer" and "junior"), not just any single word — a lone
    shared word like "software" mentioned in an unrelated posting (e.g. an
    admin job mentioning "supports our software team") was letting through
    completely irrelevant jobs when min_hits was 1.

    This is intentionally still loose at this stage — the AI match scorer
    (core/matcher.py) does the real, strict filtering later. This stage's
    only job is to not throw away good jobs before they even get scored,
    while not flooding it with obviously unrelated ones either.
    """
    text_lower = text.lower()
    for kw in keywords:
        words = [w for w in kw.lower().split() if len(w) > 2 and w not in _STOPWORDS]
        hits = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text_lower))
        if hits >= min(min_hits, len(words)):  # short keywords (1-2 words) still need all their words
            return True
    return False
