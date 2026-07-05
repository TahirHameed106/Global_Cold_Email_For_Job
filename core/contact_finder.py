"""
contact_finder.py — Free Email Pattern Detector + SMTP Verifier
No paid API needed. Two jobs:

  1. detect_company_pattern() — find 1-2 REAL emails a company already
     published (team page, about page, impressum, GitHub org) and figure out
     their email format (first.last@ / firstlast@ / first@ / etc).

  2. verify_email() — before sending, do a free "would this address bounce?"
     check using an SMTP handshake, without actually sending anything.

This does NOT scrape LinkedIn or guess personal emails that were never
published anywhere. It only reverse-engineers a pattern from emails the
company itself put on its own website.
"""

import re
import smtplib
import socket
import time
from email.utils import parseaddr

import requests
from bs4 import BeautifulSoup

try:
    import dns.resolver
    HAVE_DNS = True
except ImportError:
    HAVE_DNS = False
    print("[contact_finder] dnspython not installed — run: pip install dnspython")


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Pages likely to have a named person next to their real email.
# 'impressum' is a legal requirement on German/Austrian sites — great free source.
SEED_PATHS = ["/team", "/about", "/about-us", "/contact", "/impressum", "/imprint", "/leadership"]


# ─── Step 1: collect seed emails from the company's own site ──────────────

def get_page_emails_with_context(url):
    """
    Fetch a page and return a list of (email, surrounding_text) tuples.
    surrounding_text helps us guess whose email it is (crude but free).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        results = []
        for match in re.finditer(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text):
            email = match.group(0)
            start = max(0, match.start() - 60)
            context = text[start:match.start()]
            results.append((email, context))
        return results
    except Exception:
        return []


def collect_seed_emails(domain, max_pages=5):
    """Visit a handful of likely pages on the company's own site and collect real emails."""
    seeds = []
    base = f"https://{domain}"
    for path in SEED_PATHS[:max_pages]:
        seeds.extend(get_page_emails_with_context(base + path))
        time.sleep(1)  # be polite, avoid hammering their server
    # Keep only emails actually at this domain (not third-party tools like sentry/wixpress)
    seeds = [(e, ctx) for e, ctx in seeds if e.lower().endswith("@" + domain.lower())]
    return list(set(seeds))


# ─── Step 2: figure out the pattern from seed emails + known names ────────

def infer_pattern(first_name, last_name, email):
    """Given a known person's name and their real email, return the pattern key, or None."""
    local = email.split("@")[0].lower()
    f, l = first_name.lower().strip(), last_name.lower().strip()
    if not f or not l:
        return None

    candidates = {
        "first.last":  f"{f}.{l}",
        "firstlast":   f"{f}{l}",
        "flast":       f"{f[0]}{l}",
        "first_last":  f"{f}_{l}",
        "last.first":  f"{l}.{f}",
        "first":       f,
        "last":        l,
    }
    for pattern, value in candidates.items():
        if local == value:
            return pattern
    return None


def detect_company_pattern(domain, known_people=None):
    """
    known_people: optional list of (first_name, last_name) you already found
    (e.g. from the company's own team page, or a GitHub org member list).

    Returns: {"pattern": "first.last" | None, "confidence": "confirmed"|"likely"|"none",
              "seed_emails": [...]}
    """
    seeds = collect_seed_emails(domain)
    seed_emails = [e for e, _ in seeds]

    if not known_people:
        # No names to pair with — we can still report seeds found, but can't infer pattern
        return {"pattern": None, "confidence": "none", "seed_emails": seed_emails}

    matched_patterns = []
    for first, last in known_people:
        for email in seed_emails:
            p = infer_pattern(first, last, email)
            if p:
                matched_patterns.append(p)

    if not matched_patterns:
        return {"pattern": None, "confidence": "none", "seed_emails": seed_emails}

    # Most common pattern across all matches
    best_pattern = max(set(matched_patterns), key=matched_patterns.count)
    confidence = "confirmed" if matched_patterns.count(best_pattern) >= 2 else "likely"

    return {"pattern": best_pattern, "confidence": confidence, "seed_emails": seed_emails}


def build_email(first_name, last_name, domain, pattern):
    """Build a candidate email address from a name + confirmed/likely pattern."""
    f, l = first_name.lower().strip(), last_name.lower().strip()
    templates = {
        "first.last": f"{f}.{l}",
        "firstlast":  f"{f}{l}",
        "flast":      f"{f[0]}{l}",
        "first_last": f"{f}_{l}",
        "last.first": f"{l}.{f}",
        "first":      f,
        "last":       l,
    }
    local = templates.get(pattern)
    if not local:
        return None
    return f"{local}@{domain}"


# ─── Step 3: free SMTP verification (no email actually sent) ──────────────

_mx_cache = {}
_catchall_cache = {}


def get_mx_host(domain):
    """Look up the mail server for a domain. Cached per run."""
    if domain in _mx_cache:
        return _mx_cache[domain]
    if not HAVE_DNS:
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx_host = str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip(".")
        _mx_cache[domain] = mx_host
        return mx_host
    except Exception:
        _mx_cache[domain] = None
        return None


def _smtp_check(mx_host, address, from_address="check@example.com", timeout=8):
    """
    Open an SMTP connection and ask 'would you accept mail for this address?'
    without sending DATA (so no email is actually delivered).
    Returns the RCPT TO response code (int), or None if the check failed/timed out.
    """
    try:
        server = smtplib.SMTP(timeout=timeout)
        server.connect(mx_host, 25)
        server.helo("checker.local")
        server.mail(from_address)
        code, _ = server.rcpt(address)
        server.quit()
        return code
    except (socket.error, smtplib.SMTPException, OSError):
        return None


def is_catch_all(domain, mx_host):
    """Check whether this domain accepts mail for ANY address (making verification useless)."""
    if domain in _catchall_cache:
        return _catchall_cache[domain]
    fake_address = f"definitely-not-a-real-person-zzq7x9@{domain}"
    code = _smtp_check(mx_host, fake_address)
    result = code in (250, 251)
    _catchall_cache[domain] = result
    return result


def verify_email(email):
    """
    Check if a guessed email is likely to bounce, for free.

    Returns one of:
      "valid"      — server confirmed the mailbox exists
      "invalid"    — server confirmed it does NOT exist (do not send)
      "catch_all"  — domain accepts anything, can't verify (use judgement / fallback)
      "unknown"    — couldn't check (port 25 blocked, timeout, temp server error)
    """
    domain = email.split("@")[-1]
    mx_host = get_mx_host(domain)
    if not mx_host:
        return "unknown"

    if is_catch_all(domain, mx_host):
        return "catch_all"

    code = _smtp_check(mx_host, email)
    if code in (250, 251):
        return "valid"
    if code in (550, 551, 553):
        return "invalid"
    return "unknown"  # includes 450/451 (temporary) and blocked/timeout cases


# ─── Quick manual test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    domain = "example.com"
    print(f"Testing pattern detection for {domain}...")
    result = detect_company_pattern(domain, known_people=[("Jane", "Smith")])
    print(result)

    test_email = f"jane.smith@{domain}"
    print(f"Verifying {test_email} -> {verify_email(test_email)}")
    print("Note: port 25 is blocked on many cloud/VPS networks — 'unknown' there is expected, not a bug.")
