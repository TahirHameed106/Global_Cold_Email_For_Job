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
import yaml
import schedule as schedule_lib
from dotenv import load_dotenv

load_dotenv()

from sources import remoteok, weworkremotely, himalayas, wellfound
from core.normalizer import dedupe, filter_jobs
from core.matcher import score_match
from core.cv_tailor import build_tailored_cv_data, render_cv_docx
from core.contact_finder import detect_company_pattern, build_email, verify_email
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

    all_jobs = []
    for name, enabled in profile["sources"].items():
        if not enabled:
            continue
        module = SOURCE_MODULES.get(name)
        if not module:
            print(f"[main] Unknown source '{name}' in profile.yaml, skipping.")
            continue
        print(f"\n── Source: {name} ──")
        jobs = module.fetch_jobs(keywords=keywords, employment_types=emp_types, max_jobs=max_per_source)
        all_jobs.extend(jobs)

    return all_jobs


def guess_company_domain(job):
    """If a source didn't give us a domain, make a best-effort guess from the company name."""
    if job.get("company_domain"):
        return job["company_domain"]
    slug = "".join(ch for ch in job["company"].lower() if ch.isalnum())
    return f"{slug}.com"


def find_best_contact(job, contact_priority):
    """
    Returns (email, confidence_label) using only legitimate, free sources:
    company's own site pattern detection + free SMTP verification.
    Never scrapes LinkedIn or guesses a named individual's personal email
    without first confirming a real pattern from the company's own site.
    """
    domain = guess_company_domain(job)

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

    if verdict in ("valid", "catch_all", "unknown"):
        confidence = "catchall_fallback" if verdict == "catch_all" else "guessed_unconfirmed"
        return fallback, confidence

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

        subject = f"{job['title']} application — {candidate['name']}"
        body = (
            f"Hi,\n\n"
            f"I'm {candidate['name']}, {candidate['headline']}. "
            f"I came across the {job['title']} opening at {job['company']} and wanted to apply directly.\n\n"
            f"My background lines up closely with what you're looking for "
            f"({', '.join(match['matching_skills'][:4])}), and I've attached a CV tailored to this role.\n\n"
            f"Would love the chance to talk. Thanks for your time.\n\n"
            f"Best,\n{candidate['name']}"
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
