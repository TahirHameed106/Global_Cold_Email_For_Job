"""
normalizer.py — Dedupe jobs across sources and filter by the profile's
company-size / employment-type / country preferences.
"""

import re


_EMPLOYMENT_TYPE_PATTERNS = {
    "internship": [
        r"\bintern(?:ship)?\b",
        r"\btrainee\b",
        r"\bapprentice\b",
        r"\bco[-\s]?op\b",
        r"\bworking\s+student\b",
        r"\bstudent\s+worker\b",
    ],
    "junior": [
        r"\bjunior\b",
        r"\bjr\.?\b",
        r"\bentry[-\s]level\b",
        r"\bnew[-\s](?:grad|graduate)\b",
        r"\bfresher\b",
        r"\bassociate\s+(?:engineer|developer|software\s+engineer|software\s+developer)\b",
    ],
    "volunteer": [
        r"\bvolunteer(?:ing|ed)?\b",
        r"\bunpaid\b",
        r"\bpro\s+bono\b",
        r"\bcommunity\s+contributor\b",
        r"\bopen\s+source\s+contributor\b",
    ],
}


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


def _employment_type_matches(job, wanted_types):
    """
    Most sources don't cleanly tag employment type, so we check the title
    and description text for the wanted keywords too.
    """
    text = f"{job['title']} {job['description']}".lower()
    for wanted_type in wanted_types:
        patterns = _EMPLOYMENT_TYPE_PATTERNS.get(wanted_type.lower(), [rf"\b{re.escape(wanted_type.lower())}\b"])
        if any(re.search(pattern, text) for pattern in patterns):
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
