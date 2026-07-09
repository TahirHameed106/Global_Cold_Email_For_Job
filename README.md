# Global Job Application Bot

A field-agnostic job search bot. Change `config/profile.yaml` to retarget it
to any field, country, seniority level, or company size — no code changes.

Currently configured for: junior/intern/volunteer software engineering roles,
remote-first, at 1-10 person startups, across UK / USA / Germany / UAE /
Saudi Arabia / Australia / Austria.

## How it works

1. **`config/profile.yaml`** — your search criteria (field, keywords, countries, company size, threshold)
2. **`data/skill_bank.json`** — the ONLY source of truth for your real skills/projects/experience. Nothing is ever invented outside this file.
3. **`sources/`** — pulls jobs from RemoteOK, We Work Remotely, Himalayas, Adzuna, and Jooble (all free, legitimate APIs — no login/scraping risk). Wellfound and LinkedIn are manual-assist stubs — see below.
4. **`core/matcher.py`** — scores each job against your skill bank, 0-100%
5. **`core/cv_tailor.py`** — for jobs scoring above your threshold, reorders and rephrases your real bullets to mirror the job's language, then renders a `.docx`
6. **`core/contact_finder.py`** — finds a real, company-published email (never scrapes LinkedIn), and free-verifies it won't bounce
7. **`core/sender.py`** — sends via Gmail with a human-like delay
8. **`core/tracker.py`** — logs every attempt to `data/applications.csv`, tracks confidence + replies
9. **`core/reply_tracker.py`** — run separately to check your inbox and auto-mark replies / auto-unsubscribe people who ask to stop

## Setup

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
# then fill in .env with your Gemini API key + Gmail App Password
```

Edit `data/skill_bank.json` with your real skills, projects, and experience —
be thorough, this is what every tailored CV is built from.

Edit `config/profile.yaml` to match what you're targeting.

For Indeed-style coverage, sign up free for:
- Adzuna: https://developer.adzuna.com/ (covers UK, US, Germany, Austria, Australia)
- Jooble: https://jooble.org/api/about (broader coverage, best for UAE/Saudi Arabia)

Add both sets of keys to `.env`.

## Running

```bash
python main.py              # run once, right now
python main.py schedule     # run once, then daily at 09:00
python -m core.reply_tracker   # check inbox for replies (run this daily too)
```

## About Wellfound and LinkedIn

Neither has a public jobs-search API for regular developers, and both
explicitly prohibit automated scraping in their Terms of Service — LinkedIn
in particular has pursued legal action against scraping tools before. So
instead of scraping them:

1. Browse them normally in your browser with their own built-in filters
   (Remote, 1-10 employees / Internship-Entry level, your keywords)
2. For roles you like on Wellfound: message the founder directly through
   Wellfound's own messaging (often more effective than email), or paste
   the job into `data/manual_jobs.json`
3. For roles you like on LinkedIn: paste the job into
   `data/manual_jobs_linkedin.json`
4. Either way, it then runs through the exact same match/tailor/contact/
   send/track pipeline as everything else

## Honesty guardrails (please don't remove these)

- `cv_tailor.py` only rephrases and reorders bullets already in
  `skill_bank.json` — it has a safety check that discards any AI rewrite
  that introduces unfamiliar technical terms
- `contact_finder.py` only uses emails a company published themselves
  (team/about/impressum pages), plus a free bounce-check before sending —
  it does not scrape LinkedIn or guess individual employees' personal emails
- `tracker.py` respects `data/unsubscribed.csv` permanently — anyone who
  replies asking to stop is auto-added by `reply_tracker.py` and never
  contacted again

## Known limitations to check before relying on this daily

- **Himalayas API schema** — I could not verify the current live field names
  from this environment. Run `python -m sources.himalayas` once; it prints
  the raw JSON shape of one job so you can confirm/adjust the field names in
  `sources/himalayas.py` if they've changed.
- **SMTP verification (port 25)** — many cloud hosts (AWS, GCP, most VPS
  providers) block outbound port 25 by default. If you deploy this on a
  cloud server, `verify_email()` will return `"unknown"` instead of
  crashing — this is expected, not a bug. Runs fine from a home internet
  connection.
- **Company size data** — RemoteOK and We Work Remotely don't reliably
  report team size, so those jobs pass through as `size_unknown` rather
  than being filtered out. Worth a quick manual check on the company's site
  before applying if size really matters to you.
- **Legal note** — cold-emailing individuals (vs. company-published
  addresses) carries different rules under GDPR (UK/Germany/Austria) than
  in Pakistan. This bot is built to only use company-published contacts —
  keep it that way.
