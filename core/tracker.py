"""
tracker.py — Application Tracker
Logs every application to CSV, prevents duplicate sends, and now also tracks:
  - email_confidence : how sure we are the address is real
                        (confirmed_pattern / guessed_unconfirmed / catchall_fallback / careers_generic)
  - replied_at        : when the recipient actually replied (blank if no reply yet)
  - reply_snippet     : first ~200 characters of their reply, so you can skim without opening Gmail

Old applications.csv files (from before this update) are auto-upgraded the
first time you run this file — missing columns are added with blank values,
nothing existing is deleted or changed.
"""

import os
import csv
from datetime import datetime

# Absolute paths so this works no matter what directory you run main.py from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
os.makedirs(_DATA_DIR, exist_ok=True)

TRACKER_FILE = os.path.join(_DATA_DIR, "applications.csv")
UNSUBSCRIBE_FILE = os.path.join(_DATA_DIR, "unsubscribed.csv")

COLUMNS = [
    "date", "time", "company", "job_title", "location",
    "email_sent_to", "phone", "cv_used", "subject",
    "status", "job_url", "notes",
    "email_confidence", "replied_at", "reply_snippet"
]


# ─── Unsubscribe list ──────────────────────────────────────────────────────

def add_unsubscribe(email):
    """Add an email address to the permanent do-not-contact list."""
    email = email.lower().strip()
    existing = get_unsubscribed()
    if email in existing:
        return
    write_header = not os.path.exists(UNSUBSCRIBE_FILE)
    with open(UNSUBSCRIBE_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["email", "date_added"])
        writer.writerow([email, datetime.now().strftime("%Y-%m-%d")])
    print(f"[tracker] Added to unsubscribe list: {email}")


def get_unsubscribed():
    """Return a set of all unsubscribed email addresses (lowercased)."""
    if not os.path.exists(UNSUBSCRIBE_FILE):
        return set()
    with open(UNSUBSCRIBE_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["email"].lower().strip() for row in reader}


def is_unsubscribed(email):
    return email.lower().strip() in get_unsubscribed()


# ─── Core tracker file handling (with auto-migration) ─────────────────────

def init_tracker():
    """Create the CSV file with headers if it doesn't exist."""
    if not os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
        print(f"[tracker] Created {TRACKER_FILE}")
    else:
        _migrate_if_needed()


def _migrate_if_needed():
    """
    If applications.csv exists but is missing the newer columns
    (email_confidence, replied_at, reply_snippet), rewrite it with those
    columns added and blank for old rows. Safe to run every time — it's a
    no-op once the file is already up to date.
    """
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)

    if set(COLUMNS) == set(existing_fields):
        return  # already up to date

    missing = [c for c in COLUMNS if c not in existing_fields]
    print(f"[tracker] Upgrading applications.csv — adding columns: {missing}")

    for row in rows:
        for col in missing:
            row[col] = ""

    with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def log_application(company, job_title, location="", email="", phone="",
                     cv_used="", subject="", status="Sent", job_url="", notes="",
                     email_confidence=""):
    """
    Log a sent (or failed) application to the CSV file.

    email_confidence: one of
        "confirmed_pattern"   — pattern verified against 2+ real seed emails
        "guessed_unconfirmed" — single-seed or SMTP-checked guess
        "catchall_fallback"   — domain accepts anything, couldn't verify, used careers@ instead
        "careers_generic"     — company-published careers@/hr@ address (always safe)

    Returns:
        dict: The logged record
    """
    init_tracker()

    now = datetime.now()
    record = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "company": company,
        "job_title": job_title,
        "location": location,
        "email_sent_to": email,
        "phone": phone,
        "cv_used": cv_used,
        "subject": subject,
        "status": status,
        "job_url": job_url,
        "notes": notes,
        "email_confidence": email_confidence,
        "replied_at": "",
        "reply_snippet": "",
    }

    with open(TRACKER_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(record)

    print(f"[tracker] Logged: {company} | {job_title} | {email or phone} | status={status}")
    return record


def already_applied(company, job_title):
    """
    True if a real (status=Sent) application already exists for this
    company+role. A past 'Failed' attempt does NOT block a retry.
    """
    if not os.path.exists(TRACKER_FILE):
        return False

    company_clean = company.lower().strip()
    title_clean = job_title.lower().strip()

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("company", "").lower().strip() == company_clean and
                    row.get("job_title", "").lower().strip() == title_clean and
                    row.get("status", "").strip().lower() == "sent"):
                return True
    return False


def update_status(company, job_title, new_status, notes=""):
    """Update the status of an application by company+job_title (e.g., 'Interview')."""
    return _update_rows(
        match_fn=lambda row: (row["company"].lower() == company.lower() and
                               row["job_title"].lower() == job_title.lower()),
        updates={"status": new_status, **({"notes": notes} if notes else {})},
        log_label=f"{company} | {job_title} -> {new_status}"
    )


def mark_replied(email_sent_to, reply_snippet="", reply_date=None):
    """
    Mark an application as Replied, matched by the recipient's email address
    (this is how reply_tracker.py finds which sent application a reply belongs to,
    since we may not have a clean thread ID from Gmail).

    Only updates rows currently in status 'Sent' — won't overwrite an
    already-Replied row so the *first* reply's snippet/date is preserved.
    """
    reply_date = reply_date or datetime.now().strftime("%Y-%m-%d %H:%M")

    def match(row):
        return (row.get("email_sent_to", "").lower().strip() == email_sent_to.lower().strip()
                and row.get("status", "").strip().lower() == "sent")

    updated = _update_rows(
        match_fn=match,
        updates={
            "status": "Replied",
            "replied_at": reply_date,
            "reply_snippet": reply_snippet[:200],
        },
        log_label=f"Reply matched -> {email_sent_to}",
        first_match_only=True,
    )
    return updated


def _update_rows(match_fn, updates, log_label="", first_match_only=False):
    """Shared helper: rewrite applications.csv applying `updates` to matching rows."""
    if not os.path.exists(TRACKER_FILE):
        print("[tracker] No tracker file found.")
        return False

    rows = []
    updated = False

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if match_fn(row) and (not first_match_only or not updated):
                row.update(updates)
                updated = True
            rows.append(row)

    if updated:
        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[tracker] Updated: {log_label}")
    else:
        print(f"[tracker] No matching record found: {log_label}")

    return updated


def get_pending_sent_emails():
    """
    Return [{email, company, job_title, date}] for every application still
    in status 'Sent' (i.e. no reply recorded yet). reply_tracker.py checks
    incoming mail against this list.
    """
    if not os.path.exists(TRACKER_FILE):
        return []

    pending = []
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status", "").strip().lower() == "sent"
                    and row.get("email_sent_to", "").strip()):
                pending.append({
                    "email": row["email_sent_to"].strip(),
                    "company": row["company"],
                    "job_title": row["job_title"],
                    "date": row["date"],
                })
    return pending


def get_stats():
    """Print a summary of all applications, including reply rate."""
    if not os.path.exists(TRACKER_FILE):
        print("[tracker] No applications logged yet.")
        return

    stats = {}
    total = 0
    sent_total = 0

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            status = row.get("status", "Unknown")
            stats[status] = stats.get(status, 0) + 1
            if status in ("Sent", "Replied", "Interview", "Offer", "Rejected"):
                sent_total += 1

    replied = sum(v for k, v in stats.items() if k in ("Replied", "Interview", "Offer"))
    reply_rate = (replied / sent_total * 100) if sent_total else 0

    print("\n" + "=" * 40)
    print("  APPLICATION STATS")
    print("=" * 40)
    print(f"  Total logged        : {total}")
    for status, count in sorted(stats.items()):
        print(f"    {status:<10}: {count}")
    print(f"  Reply rate          : {reply_rate:.1f}%  ({replied}/{sent_total} sent)")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    log_application(
        company="Test Startup",
        job_title="Junior Software Engineer",
        email="founder@teststartup.com",
        cv_used="general",
        subject="Application for Junior Software Engineer",
        status="Sent",
        email_confidence="confirmed_pattern",
    )
    print("Duplicate check:", already_applied("Test Startup", "Junior Software Engineer"))
    print("Pending:", get_pending_sent_emails())
    mark_replied("founder@teststartup.com", reply_snippet="Thanks for reaching out, can we schedule a call?")
    get_stats()
