"""
reply_tracker.py — Checks your Gmail inbox for replies to sent applications
and updates applications.csv automatically.

How it matches a reply to a sent application:
  We don't rely on email threading (subjects get mangled, some clients strip
  headers) — instead we just check: "did this incoming email come FROM an
  address we have logged as status=Sent?" That's reliable and simple.

Also auto-detects "please stop emailing me" style replies and adds that
address to the permanent unsubscribe list, so you never contact them again.

Run manually from the project root:
    python -m core.reply_tracker

Or schedule it (e.g. once every morning) alongside main.py.
"""

import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from core.tracker import get_pending_sent_emails, mark_replied, add_unsubscribe

IMAP_SERVER = "imap.gmail.com"

UNSUBSCRIBE_PHRASES = [
    "unsubscribe", "please remove me", "stop emailing", "do not contact",
    "don't contact", "remove me from", "no longer interested in receiving",
    "please don't email", "opt out",
]


def _decode(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded += text.decode(enc or "utf-8", errors="ignore")
        else:
            decoded += text
    return decoded


def _get_body_text(msg):
    """Extract plain-text body from an email.message.Message, best-effort."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    continue
        return ""
    else:
        try:
            return msg.get_payload(decode=True).decode(errors="ignore")
        except Exception:
            return ""


def check_replies(days_back=14, mark_as_seen=False):
    """
    Connect to Gmail via IMAP, look at recent inbox messages, and match
    senders against pending (status=Sent) applications. Updates
    applications.csv for every match found.

    Returns: number of new replies matched.
    """
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")  # same App Password used for SMTP works for IMAP

    if not gmail_address or not gmail_password:
        print("[reply_tracker] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env")
        return 0

    pending = get_pending_sent_emails()
    if not pending:
        print("[reply_tracker] No pending applications to check against.")
        return 0

    pending_emails = {p["email"].lower().strip() for p in pending}
    print(f"[reply_tracker] Checking inbox against {len(pending_emails)} pending sent application(s)...")

    matched_count = 0

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(gmail_address, gmail_password)
        mail.select("INBOX")

        since_date = datetime.now().strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(SINCE "{since_date if days_back == 0 else _n_days_ago(days_back)}")')

        if status != "OK":
            print("[reply_tracker] IMAP search failed.")
            return 0

        message_ids = data[0].split()
        print(f"[reply_tracker] {len(message_ids)} message(s) in the lookback window.")

        for msg_id in message_ids:
            fetch_cmd = "(RFC822)" if not mark_as_seen else "(BODY.PEEK[])"
            status, msg_data = mail.fetch(msg_id, fetch_cmd)
            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            from_header = _decode(msg.get("From", ""))
            from_email = from_header.split("<")[-1].replace(">", "").strip().lower()

            if from_email not in pending_emails:
                continue

            body = _get_body_text(msg)
            snippet = " ".join(body.split())[:200]

            was_updated = mark_replied(from_email, reply_snippet=snippet)
            if was_updated:
                matched_count += 1
                print(f"[reply_tracker] Reply matched: {from_email}")

            if any(phrase in body.lower() for phrase in UNSUBSCRIBE_PHRASES):
                add_unsubscribe(from_email)
                print(f"[reply_tracker] Unsubscribe request detected from {from_email} — added to do-not-contact list.")

        mail.logout()

    except imaplib.IMAP4.error as e:
        print(f"[reply_tracker] IMAP login/auth error: {e}")
        print("   -> Make sure IMAP is enabled in Gmail settings, and you're using an App Password.")
    except Exception as e:
        print(f"[reply_tracker] Unexpected error: {e}")

    print(f"[reply_tracker] Done — {matched_count} new repl{'y' if matched_count == 1 else 'ies'} recorded.")
    return matched_count


def _n_days_ago(days):
    from datetime import timedelta
    return (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")


if __name__ == "__main__":
    check_replies(days_back=14)
