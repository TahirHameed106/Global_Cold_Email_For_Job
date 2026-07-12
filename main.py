"""
main.py — Global Job Application Bot Orchestrator

Pipeline:
  1. Load your profile.yaml (field, countries, team size, keywords)
  2. Pull jobs from every enabled source (sources/*.py)
  3. Normalize, dedupe, filter by employment type + company size
  4. Score each job against your skill_bank.json (core/matcher.py)
  5. For jobs scoring >= match_threshold_percent, tailor a CV (core/cv_tailor.py)
  6. Find the best contact (founder/job-poster/careers@) + free-verify it
     (core/contact_finder.py)
  7. Send the email with the tailored CV attached (core/sender.py)
  8. Log everything (core/tracker.py)

Run:
    python main.py            → runs once
    python main.py schedule   → runs once now, then daily at the configured time

Check for replies separately, any time:
    python -m core.reply_tracker
"""

import os
import sys
import time
import json
import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import yaml
import schedule as schedule_lib
from dotenv import load_dotenv

load_dotenv()

from sources import remoteok, weworkremotely, himalayas, wellfound, adzuna, jooble, linkedin, remotive, arbeitnow, jobicy
from core.normalizer import dedupe, filter_jobs
from core.matcher import score_match
from core.cv_tailor import build_tailored_cv_data, render_cv_docx
from core.contact_finder import detect_company_pattern, build_email, verify_email, has_mx
from core.sender import send_with_delay
from core.tracker import log_application, already_applied, is_unsubscribed, get_stats

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
GENERATED_CV_DIR = os.path.join(PROJECT_ROOT, "data", "generated_cvs")
os.makedirs(GENERATED_CV_DIR, exist_ok=True)

SOURCE_MODULES = {
    "remoteok": remoteok,
    "weworkremotely": weworkremotely,
    "himalayas": himalayas,
    "wellfound": wellfound,
    "adzuna": adzuna,
    "jooble": jooble,
    "linkedin": linkedin,
    "remotive": remotive,
    "arbeitnow": arbeitnow,
    "jobicy": jobicy,
}


def load_profile():
    path = os.path.join(PROJECT_ROOT, "config", "profile.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_skill_bank():
    path = os.path.join(PROJECT_ROOT, "data", "skill_bank.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_jobs(profile):
    search = profile["search"]
    limits = profile["limits"]
    keywords = search["keywords"]
    emp_types = search["employment_types"]
    max_per_source = limits["max_jobs_per_source"]
    target_countries = search.get("target_countries", [])

    all_jobs = []
    for name, enabled in profile["sources"].items():
        if not enabled:
            continue
        module = SOURCE_MODULES.get(name)
        if not module:
            print(f"[main] Unknown source '{name}' in profile.yaml, skipping.")
            continue
        print(f"\n── Source: {name} ──")
        jobs = module.fetch_jobs(
            keywords=keywords,
            employment_types=emp_types,
            max_jobs=max_per_source,
            target_countries=target_countries,   # used by adzuna; ignored elsewhere via **kwargs
            locations=target_countries,           # used by jooble; ignored elsewhere via **kwargs
        )
        all_jobs.extend(jobs)

    return all_jobs


JOB_BOARD_DOMAINS = {"remoteok.com", "weworkremotely.com", "himalayas.app",
                      "adzuna.com", "indeed.com", "linkedin.com", "wellfound.com",
                      "remotive.com", "arbeitnow.com", "jobicy.com"}

# Domains that show up as outbound links but aren't the company's own site —
# social media, trackers, generic ATS platforms hosting the application form
# rather than the company's real domain.
NOT_COMPANY_DOMAINS = JOB_BOARD_DOMAINS | {
    "twitter.com", "x.com", "linkedin.com", "facebook.com", "instagram.com",
    "youtube.com", "github.com", "google.com", "google-analytics.com",
}


def _find_outbound_company_link(listing_page_url):
    """
    For job boards (like WeWorkRemotely) whose own URL is just their listing
    page — not a redirect to the company — fetch that page's HTML and look
    for the actual outbound "Apply" link, which usually points to the real
    company site or careers page.
    """
    try:
        resp = requests.get(listing_page_url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"})
        soup = BeautifulSoup(resp.text, "html.parser")

        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            domain = urlparse(href).netloc.replace("www.", "")
            if not domain or any(nd in domain for nd in NOT_COMPANY_DOMAINS):
                continue
            link_text = a.get_text(strip=True).lower()
            # Strongly prefer a link whose visible text says "apply" — that's
            # almost always the real outbound link to the company
            priority = 0 if "apply" in link_text else 1
            candidates.append((priority, domain))

        if candidates:
            candidates.sort(key=lambda c: c[0])
            return candidates[0][1]
    except Exception:
        pass
    return None


def resolve_real_domain(job):
    """
    Get the company's ACTUAL domain instead of guessing one from their name.

    Two-tier resolution:
      1. Follow the job URL's redirect chain — works when the URL already
         points straight to the company (RemoteOK's apply_url, Adzuna's
         redirect_url, etc.)
      2. If that lands back on the job board itself (e.g. WeWorkRemotely's
         RSS link is just their own listing page, not a redirect), fetch
         that listing page's HTML and look for the actual outbound "Apply"
         link, which points to the real company site.

    Falls back to a name-based guess ONLY if both tiers fail, and that guess
    is validated by has_mx() before ever being used to send.
    """
    if job.get("company_domain"):
        return job["company_domain"]

    job_url = job.get("job_url", "")
    if job_url:
        try:
            resp = requests.head(job_url, allow_redirects=True, timeout=10,
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; JobSearchBot/1.0)"})
            final_domain = urlparse(resp.url).netloc.replace("www.", "")
            if final_domain and not any(jb in final_domain for jb in JOB_BOARD_DOMAINS):
                return final_domain
        except Exception:
            pass  # falls through to tier 2 below

        # Tier 2 — the URL just led back to the job board itself; scrape
        # that listing page for the real outbound company link instead.
        outbound_domain = _find_outbound_company_link(job_url)
        if outbound_domain:
            return outbound_domain

    # Last resort: guess from company name, stripping parenthetical region
    # tags like "(MENA)" or "(UK)" that aren't part of the actual brand name
    company_clean = re.sub(r"\([^)]*\)", "", job["company"]).strip()
    slug = "".join(ch for ch in company_clean.lower() if ch.isalnum())
    return f"{slug}.com"


def find_best_contact(job, contact_priority):
    """
    Returns (email, confidence_label) using only legitimate, free sources:
    company's own site pattern detection + free SMTP verification.
    Never scrapes LinkedIn or guesses a named individual's personal email
    without first confirming a real pattern from the company's own site.

    IMPORTANT: if the domain doesn't even have a mail server (has_mx is
    False), we do NOT send — a guessed domain that doesn't exist at all is
    a certain bounce, not an "unknown, might as well try."
    """
    domain = resolve_real_domain(job)

    if not has_mx(domain):
        print(f"[main] '{domain}' has no mail server at all — skipping, not guessing further.")
        return None, "none"

    pattern_info = detect_company_pattern(domain, known_people=None)
    seed_emails = pattern_info.get("seed_emails", [])

    if seed_emails:
        # We found at least one real, company-published address — prefer the
        # most HR/careers/founder-looking one from what's actually published.
        priority_terms = ["founder", "ceo", "hr", "careers", "hiring", "jobs", "recruit"]

        def score(e):
            local = e.split("@")[0].lower()
            for i, term in enumerate(priority_terms):
                if term in local:
                    return i
            return len(priority_terms)

        best = sorted(seed_emails, key=score)[0]
        return best, "careers_generic"

    # No real published email found on the company site — fall back to the
    # generic careers@ guess, and free-verify it before use.
    fallback = f"careers@{domain}"
    verdict = verify_email(fallback)
    if verdict == "invalid":
        fallback = f"hello@{domain}"
        verdict = verify_email(fallback)

    # Only "valid" or "catch_all" (domain exists, mailbox check inconclusive)
    # are acceptable now. A domain that resolves but where we truly can't
    # confirm ANY mailbox status ("unknown" for reasons other than no-MX,
    # e.g. the receiving server timed out) is now also rejected rather than
    # guessed-and-sent — since we already confirmed the domain is real via
    # has_mx() above, "unknown" here means the specific mailbox is unconfirmed,
    # which is still too risky for a guessed address.
    if verdict == "valid":
        return fallback, "guessed_unconfirmed"
    if verdict == "catch_all":
        return fallback, "catchall_fallback"

    print(f"[main] Could not confirm any mailbox at '{domain}' (verdict: {verdict}) — skipping rather than guessing blind.")
    return None, "none"


def run_pipeline():
    profile = load_profile()
    skill_bank = load_skill_bank()
    candidate = profile["candidate"]
    limits = profile["limits"]
    threshold = profile["search"]["match_threshold_percent"]

    print("=" * 60)
    print(f"  Global Job Bot — {candidate['name']}")
    print(f"  Field: {profile['search']['field']}")
    print(f"  Match threshold: {threshold}%  |  Max emails/day: {limits['max_emails_per_day']}")
    print("=" * 60)

    print("\n── STEP 1: Collecting jobs ──")
    raw_jobs = collect_jobs(profile)
    print(f"\n[main] {len(raw_jobs)} raw job(s) collected across all sources")

    jobs = dedupe(raw_jobs)
    jobs = filter_jobs(jobs, profile)
    print(f"[main] {len(jobs)} job(s) remain after dedupe + filters")

    emails_sent = 0

    print("\n── STEP 2: Score → Tailor → Contact → Send ──")
    for job in jobs:
        if emails_sent >= limits["max_emails_per_day"]:
            print(f"[main] Daily limit of {limits['max_emails_per_day']} reached. Stopping.")
            break

        if already_applied(job["company"], job["title"]):
            print(f"[main] Already applied -> {job['company']} ({job['title']}). Skipping.")
            continue

        print(f"\n[main] -- {job['title']} @ {job['company']} ({job['source']}) --")

        match = score_match(job["title"], job["description"], skill_bank)
        print(f"[main] Match score: {match['score']}% — {match['reasoning']}")

        if match["score"] < threshold:
            print(f"[main] Below {threshold}% threshold, skipping.")
            continue

        # Tailor the CV
        tailored = build_tailored_cv_data(job["title"], job["description"], skill_bank, match)
        cv_filename = f"{job['company']}_{job['title']}".replace(" ", "_").replace("/", "-")[:80] + ".docx"
        cv_path = os.path.join(GENERATED_CV_DIR, cv_filename)
        render_cv_docx(candidate, tailored, cv_path)

        # Find a real contact
        to_email, confidence = find_best_contact(job, profile["email"]["contact_priority"])
        if not to_email:
            print("[main] No usable contact email found, skipping.")
            continue
        if is_unsubscribed(to_email):
            print(f"[main] {to_email} previously unsubscribed, skipping.")
            continue

        top_project = tailored["projects"][0] if tailored.get("projects") else None
        edu = tailored.get("education", {})
        links = candidate.get("links", {})
        link_line = " | ".join(v for v in [links.get("github", ""), links.get("linkedin", "")] if v)

        subject = f"{job['title']} application — {candidate['name']}"
        body = (
            f"Hi,\n\n"
            f"I'm {candidate['name']}, a {candidate['headline']} based in {candidate.get('location','')}. "
            f"I came across the {job['title']} opening at {job['company']} and wanted to apply directly, "
            f"since it lines up closely with what I've been building.\n\n"
            f"A quick snapshot of relevant background: "
            f"{', '.join(match['matching_skills'][:5])}.\n\n"
        )
        if top_project:
            body += (
                f"Most relevant recent work — {top_project['title']}: "
                f"{top_project['bullets'][0]}\n\n"
            )
        if edu:
            body += (
                f"I'm currently a {edu.get('degree','')} student at {edu.get('institute','')} "
                f"(CGPA {edu.get('cgpa','')}), and comfortable working independently in a small, fast-moving team.\n\n"
            )
        body += "I've attached a CV tailored to this specific role.\n\n"
        if link_line:
            body += f"{link_line}\n\n"
        body += (
            f"Happy to jump on a quick call whenever works for you. Thanks for your time.\n\n"
            f"Best,\n{candidate['name']}\n{candidate.get('phone','')}"
        )

        success = send_with_delay(
            to_address=to_email,
            subject=subject,
            body=body,
            cv_path=cv_path,
            sender_email=os.getenv("GMAIL_ADDRESS"),
            sender_password=os.getenv("GMAIL_APP_PASSWORD"),
            candidate_name=candidate["name"],
        )

        log_application(
            company=job["company"],
            job_title=job["title"],
            location=job.get("location", ""),
            email=to_email if success else "",
            cv_used=cv_filename,
            subject=subject,
            status="Sent" if success else "Failed",
            job_url=job.get("job_url", ""),
            notes=f"{job['source']} | match {match['score']}%",
            email_confidence=confidence,
        )

        if success:
            emails_sent += 1
            print(f"[main] Sent {emails_sent}/{limits['max_emails_per_day']} today.")

    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE — {emails_sent} application(s) sent")
    print(f"{'='*60}")
    get_stats()


def run_scheduled(run_time="09:00"):
    print(f"[main] Scheduled mode — will run daily at {run_time}")
    run_pipeline()
    schedule_lib.every().day.at(run_time).do(run_pipeline)
    print(f"[main] Next run scheduled for {run_time} tomorrow. Keep this running.")
    while True:
        schedule_lib.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    if mode == "schedule":
        run_scheduled()
    else:
        run_pipeline()
