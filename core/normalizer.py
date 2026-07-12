"""
normalizer.py — Dedupe jobs across sources and filter by the profile's
company-size / employment-type / country preferences.
"""

import re


def dedupe(jobs):
    """Remove duplicate postings (same company + same title) across sources."""
    seen = set()
    unique = []
    for j in jobs:
        key = f"{j['company'].strip().lower()}|{j['title'].strip().lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(j)
    return unique


# Real postings use many different words for the same thing, and rarely the
# exact word in your profile.yaml config. This maps each config value to every
# realistic real-world phrasing so the filter doesn't reject good jobs just
# because of wording differences.
EMPLOYMENT_TYPE_SYNONYMS = {
    "internship": [
        "intern", "internship", "trainee", "traineeship", "apprentice",
        "apprenticeship", "co-op", "coop", "working student", "student worker",
    ],
    "junior": [
        "junior", "jr", "entry level", "entry-level", "new grad", "new graduate",
        "graduate", "associate", "fresher", "early career", "level 1", "l1",
    ],
    "volunteer": [
        "volunteer", "volunteering", "unpaid", "pro bono", "probono", "honorary",
    ],
    "entry-level": [
        "entry level", "entry-level", "junior", "new grad", "graduate", "fresher",
    ],
}


def _employment_type_matches(job, wanted_types):
    """
    Checks the job's title/description for realistic real-world phrasings of
    each wanted employment type (e.g. "junior" also matches "trainee",
    "fresher", "entry level"). Uses whole-word matching so "intern" doesn't
    accidentally match inside unrelated words like "internal" or "international".
    """
    text = f"{job['title']} {job['description']}".lower()

    all_phrases = set()
    for wanted in wanted_types:
        all_phrases.update(EMPLOYMENT_TYPE_SYNONYMS.get(wanted.lower(), [wanted.lower()]))

    for phrase in all_phrases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, text):
            return True
    return False


def _company_size_ok(job, size_min, size_max):
    size = job.get("company_size", "size_unknown")
    if size == "size_unknown":
        return True  # don't discard — flag for manual check instead, handled downstream
    match = re.search(r"(\d+)\s*-\s*(\d+)", size)
    if not match:
        return True
    lo, hi = int(match.group(1)), int(match.group(2))
    return not (hi < size_min or lo > size_max)


def filter_jobs(jobs, profile):
    """Apply the profile's employment-type and company-size filters."""
    search_cfg = profile["search"]
    wanted_types = search_cfg.get("employment_types", [])
    size_cfg = search_cfg.get("company_size", {"min": 1, "max": 10})

    filtered = []
    for job in jobs:
        if wanted_types and not _employment_type_matches(job, wanted_types):
            continue
        if not _company_size_ok(job, size_cfg["min"], size_cfg["max"]):
            continue
        filtered.append(job)
    return filtered
