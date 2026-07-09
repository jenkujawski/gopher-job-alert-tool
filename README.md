# Job Alert Tool

A Python automation tool that monitors company career pages and sends email
alerts when new listings matching specific keywords are posted.

## What it does

- **Fetches** current job listings from 20+ companies across three ATS
  (applicant tracking system) platforms: Greenhouse, Lever, and Ashby --
  using each platform's public JSON API rather than HTML scraping, for
  reliability.
- **Compares** each run's results against a saved record of previously
  seen listings, so only genuinely new postings are surfaced.
- **Filters** new listings by keyword (e.g. "analyst", "data",
  "operations", "BI"), using word-boundary matching to avoid false
  positives (e.g. "BI" matching inside "Reliability").
- **Notifies** via email through Gmail's SMTP server when a new listing
  matches.

Runs automatically once an hour via GitHub Actions -- no server, no paid
hosting, no manual checking.

## Why

Job postings at competitive companies fill quickly, and platform-native
alerts (LinkedIn, Google Alerts) are often slow or incomplete. This tool
checks companies' actual career pages directly and surfaces only what's
relevant.

## Stack

- Python (`requests`, `smtplib`, `schedule`)
- GitHub Actions (scheduling + hosting)
- Greenhouse / Lever / Ashby public JSON APIs

## Setup

Requires a `config.py` (not tracked in this repo) with:
```python
GMAIL_ADDRESS = "you@gmail.com"
GMAIL_APP_PASSWORD = "your-app-password"
NOTIFY_EMAIL = "you@gmail.com"
```
When deployed via GitHub Actions, these are pulled from encrypted
repository secrets instead.
