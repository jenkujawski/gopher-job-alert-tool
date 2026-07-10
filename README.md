# Job Alert Tool

A Python automation tool that monitors company career pages and sends
scored email alerts when new listings matching specific criteria are
posted. Built from scratch to replace slow, incomplete job board alerts
with something that checks companies' actual career pages directly.

## What it does

**Fetches** current job listings from 50 companies across three ATS
(applicant tracking system) platforms -- Greenhouse, Lever, and Ashby --
using each platform's public JSON API rather than HTML scraping, for
reliability. Companies were chosen deliberately: prioritizing verified
remote-work reputations and data/analytics-relevant sectors over raw
volume.

**Compares** each run's results against a saved record of previously
seen listings, so only genuinely new postings are surfaced. This record
persists across runs via a JSON file committed back to the repository
after each check.

**Filters** new listings in two stages:
1. *Keyword match* on the job title (e.g. "analyst", "data",
   "operations", "BI"), using word-boundary matching to avoid false
   positives (e.g. "BI" incorrectly matching inside "Reliability").
2. *Hard filters* on the full job description for anything that passes
   step 1 -- remote status, salary floor, listing age, and a list of
   dealbreaker phrases (evasive salary language, on-call requirements,
   customer-service-focused roles, and others). A listing failing any
   hard filter is excluded entirely, regardless of anything else about it.

**Scores** everything that survives the hard filters, adding or
subtracting points for nice-to-haves (four-day workweek, strong PTO,
salary above a target threshold) and red flags (vague "wear many hats"
language, "unlimited PTO," and similar phrases correlated with poor
role clarity). The score and the specific reasons behind it are shown
alongside each job, not just a bare number.

**Notifies** via email through Gmail's SMTP server, sorted best-scoring
match first.

Runs automatically once an hour via GitHub Actions -- no server, no paid
hosting, no manual checking. Also runs locally with the same codebase;
an environment check (`GITHUB_ACTIONS`) determines whether the script
loops hourly on its own (local) or runs once per external trigger
(cloud, where GitHub's own scheduler handles timing).

## Why

Job postings at competitive companies fill quickly, and platform-native
alerts (LinkedIn, Google Alerts) are often slow, incomplete, or full of
noise. This tool checks companies' actual career pages directly and
applies real personal criteria -- not just keywords -- to surface what's
actually worth reading.

## Stack

- Python (`requests`, `beautifulsoup4`, `smtplib`, `schedule`, `re`)
- GitHub Actions (scheduling + hosting, triggered via cron + manual
  `workflow_dispatch`)
- Greenhouse / Lever / Ashby public JSON APIs

## Setup

Requires a `config.py` (not tracked in this repo -- see `.gitignore`)
with:
```python
GMAIL_ADDRESS = "you@gmail.com"
GMAIL_APP_PASSWORD = "your-app-password"
NOTIFY_EMAIL = "you@gmail.com"
```
When deployed via GitHub Actions, these are pulled from encrypted
repository secrets instead, and `config.py` is generated fresh on each
run -- the real credentials never live in the repository itself.

## Adding companies

Companies are defined as simple dictionaries in the `COMPANIES` list at
the top of `job_alert.py`:
```python
{"name": "Company Name", "slug": "their-ats-slug", "ats": "greenhouse"}
```
No new code required -- the fetch dispatcher automatically routes each
company to the correct API based on its `ats` value.
