"""
sources/pakistan_jobs.py — Rozee.pk scraper (Pakistan's largest job portal).

Pakistani job boards (Rozee.pk, Mustakbil.com) don't offer free public APIs
like the international sources do, so this uses Selenium to read their
public, non-login-walled search results pages — the same approach your
original project used, but with two upgrades:

  1. webdriver-manager auto-downloads the correct ChromeDriver version for
     whatever Chrome you have installed, instead of a bundled chromedriver.exe
     that goes stale every time Chrome updates.
  2. Runs headless (no visible browser window) and only reads public search
     result pages — no login, no account actions, nothing behind auth.

IMPORTANT — verify before relying on this:
Rozee.pk frequently returns Cloudflare challenge pages instead of jobs.
That means this adapter is best treated as an opt-in/manual source, not a
default automated source. Run this file directly first if you want to test
whether the site is currently reachable from your network:

    python -m sources.pakistan_jobs

It will print how many job cards it found and the raw HTML structure of
the first one. If it finds 0 jobs, Rozee.pk likely changed their page
layout — open the page in your own browser, inspect the job card elements,
and update the CSS selectors marked below.
"""

import os
import time
from .base import normalize_job, keyword_matches

ROZEE_SEARCH_URL = "https://www.rozee.pk/job/jsearch/q/{query}"
DEBUG_DUMP_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rozee_debug.html")


def _get_driver():
    """Headless Chrome via webdriver-manager — no manual driver file needed."""
    import platform
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())

    # On Windows, chromedriver.exe spawns its own visible console window by
    # default — separate from the actual (headless, invisible) Chrome
    # browser itself. That's the "black screen" popping up — it's
    # chromedriver's own log window, not an error. This suppresses it.
    if platform.system() == "Windows":
        import subprocess
        service.creation_flags = subprocess.CREATE_NO_WINDOW

    return webdriver.Chrome(service=service, options=options)


def fetch_jobs(keywords, employment_types=None, max_jobs=25, **kwargs):
    """
    Searches Rozee.pk for each keyword and returns matching jobs.
    Runs one search per keyword (first 3 keywords only, to keep runtime reasonable).
    """
    jobs = []
    seen_urls = set()

    try:
        driver = _get_driver()
    except Exception as e:
        print(f"[Rozee.pk] Could not start Chrome — is Chrome installed? ({e})")
        return jobs

    try:
        for kw in keywords[:3]:
            if len(jobs) >= max_jobs:
                break
            query = kw.replace(" ", "-")
            url = ROZEE_SEARCH_URL.format(query=query)

            try:
                driver.get(url)

                # Rozee.pk loads job listings via JavaScript after the page
                # loads — a blind sleep isn't reliable. Wait up to 10s for
                # the page to settle, using document.readyState plus extra
                # buffer time for the AJAX call to populate results.
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                time.sleep(3)  # extra buffer for the AJAX job list to render in

                page_text = driver.page_source.lower()
                if "just a moment" in page_text or "verification successful" in page_text or "cf-turnstile" in page_text:
                    print("[Rozee.pk] Cloudflare challenge detected — skipping this source.")
                    return jobs

                # SELECTOR TO VERIFY: Rozee.pk job cards. If this finds 0
                # results, inspect a live search page and update this selector.
                cards = driver.find_elements("css selector", "div.job")

                if not cards:
                    # Save what the page actually rendered so we can find the
                    # real selectors together instead of guessing blindly again.
                    os.makedirs(os.path.dirname(DEBUG_DUMP_PATH), exist_ok=True)
                    with open(DEBUG_DUMP_PATH, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print(f"[Rozee.pk] 0 job cards found with current selector. "
                          f"Saved the actual rendered page to {DEBUG_DUMP_PATH} — "
                          f"open that file, find a real job listing's HTML, and share "
                          f"the relevant snippet so the selector can be corrected.")

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        title_el = card.find_element("css selector", "h3 a")
                        title = title_el.text.strip()
                        job_url = title_el.get_attribute("href")
                        if job_url in seen_urls:
                            continue

                        company_el = card.find_elements("css selector", "div.cname a")
                        company = company_el[0].text.strip() if company_el else "Unknown"

                        description = card.text  # crude but functional — full card text as description

                        if not keyword_matches(f"{title} {description}", keywords):
                            continue

                        seen_urls.add(job_url)
                        jobs.append(normalize_job(
                            source="Rozee.pk",
                            title=title,
                            company=company,
                            company_domain="",
                            location="Pakistan",
                            remote=False,
                            employment_type="unknown",
                            description=description,
                            job_url=job_url,
                            posted="",
                            tags=[],
                        ))
                    except Exception:
                        continue  # skip malformed cards rather than crash the whole search

            except Exception as e:
                print(f"[Rozee.pk] Search failed for '{kw}': {e}")
                continue

    finally:
        driver.quit()

    print(f"[Rozee.pk] {len(jobs)} matching job(s) found")
    return jobs


if __name__ == "__main__":
    print("Testing Rozee.pk scraper with keyword 'software engineer'...")
    results = fetch_jobs(keywords=["software engineer", "junior", "intern"], max_jobs=5)
    if not results:
        print("\n0 jobs found. Check data/rozee_debug.html (just saved) — it's the")
        print("actual page the bot saw. Open it, search for a real job listing's")
        print("HTML (Ctrl+F for a known job title), and share that snippet so the")
        print("CSS selectors in this file can be corrected precisely.")
    for r in results:
        print(f"- {r['title']} @ {r['company']} | {r['job_url']}")
