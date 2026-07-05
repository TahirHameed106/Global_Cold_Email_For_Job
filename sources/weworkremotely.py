"""
sources/weworkremotely.py — We Work Remotely public RSS feed adapter.
No login, no key needed. Programming jobs feed is public and stable:
https://weworkremotely.com/categories/remote-programming-jobs.rss

WWR job titles in the RSS feed are formatted as "Company Name: Job Title" —
this adapter splits that automatically.
"""

import re
import time
import requests
import feedparser
from .base import normalize_job

FEED_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"}


def _strip_html(raw_html):
    return re.sub(r"<[^>]+>", " ", raw_html or "").strip()


def _looks_like_target(title, description, keywords):
    text = f"{title} {description}".lower()
    return any(kw.lower() in text for kw in keywords)


def fetch_jobs(keywords, employment_types=None, max_jobs=25):
    """Return a list of normalized job dicts matching any of the given keywords."""
    jobs = []
    try:
        resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"[WeWorkRemotely] Fetch failed: {e}")
        return jobs

    for entry in feed.entries:
        if len(jobs) >= max_jobs:
            break

        raw_title = entry.get("title", "")
        description = _strip_html(entry.get("summary", ""))

        if not _looks_like_target(raw_title, description, keywords):
            continue

        # WWR format: "Company Name: Job Title"
        if ":" in raw_title:
            company, title = raw_title.split(":", 1)
            company, title = company.strip(), title.strip()
        else:
            company, title = "Unknown", raw_title.strip()

        jobs.append(normalize_job(
            source="WeWorkRemotely",
            title=title,
            company=company,
            company_domain="",   # WWR doesn't expose this directly — contact_finder derives it later
            location="Remote",
            remote=True,
            employment_type="unknown",
            description=description,
            job_url=entry.get("link", ""),
            posted=entry.get("published", ""),
            tags=[],
        ))
        time.sleep(0.1)

    print(f"[WeWorkRemotely] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    results = fetch_jobs(keywords=["junior", "intern", "entry"], max_jobs=5)
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
