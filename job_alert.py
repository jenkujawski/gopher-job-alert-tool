"""
STEP 4: Send an email when matching new jobs are found.

This combines everything from before (FETCH -> COMPARE -> FILTER) and
adds the final piece: NOTIFY. If any new jobs pass the keyword filter,
send an email listing them.

Credentials live in config.py, imported below -- never hardcoded here.
"""

import requests
import json
import os
import re
import smtplib
import schedule
import time
from email.mime.text import MIMEText

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NOTIFY_EMAIL

SEEN_JOBS_FILE = "seen_jobs.json"

# Add companies here. 'ats' tells the script which fetch function to use.
# For Greenhouse: find the slug in the URL job-boards.greenhouse.io/[slug]
# For Lever: find the slug in the URL jobs.lever.co/[slug]
COMPANIES = [
    {"name": "Honeycomb", "slug": "honeycomb", "ats": "greenhouse"},
    {"name": "HappyCo", "slug": "happyco", "ats": "lever"},
    {"name": "Common Future", "slug": "commonfuture", "ats": "lever"},
    {"name": "Mews", "slug": "mewssystems", "ats": "greenhouse"},
    {"name": "Headspace", "slug": "hs", "ats": "greenhouse"},
    {"name": "Instacart", "slug": "instacart", "ats": "greenhouse"},
    {"name": "Carrot Fertility", "slug": "carrotfertility", "ats": "greenhouse"},
    {"name": "Signifyd", "slug": "signifyd95", "ats": "greenhouse"},
    {"name": "Circle.so", "slug": "circleso", "ats": "greenhouse"},
    {"name": "Nourish", "slug": "usenourish", "ats": "greenhouse"},
    {"name": "Edmentum", "slug": "edmentum", "ats": "greenhouse"},
    {"name": "Blackthorn", "slug": "blackthorn", "ats": "greenhouse"},
    {"name": "CreativeX", "slug": "creativex", "ats": "greenhouse"},
    {"name": "Renaissance Learning", "slug": "renaissancelearning-nam", "ats": "greenhouse"},
    # Ashby companies
    {"name": "Tremendous", "slug": "tremendous", "ats": "ashby"},
    {"name": "DuckDuckGo", "slug": "duck-duck-go", "ats": "ashby"},
    {"name": "Virta Health", "slug": "virtahealth", "ats": "ashby"},
    {"name": "Headway", "slug": "headway", "ats": "ashby"},
    {"name": "Hims & Hers", "slug": "hims-and-hers", "ats": "ashby"},
    # Chainlink Labs removed -- their public page works but their API
    # access is disabled, so it can't be reached this way (confirmed
    # via direct test, not a slug issue).
    {"name": "Smalls", "slug": "smalls", "ats": "ashby"},
    # Oyster's slug wasn't confirmed in the original research -- if this
    # one prints a warning/error when you run the script, that's why.
    # We can look up the correct slug together if it fails.
    {"name": "Oyster", "slug": "oyster", "ats": "ashby"},
]

KEYWORDS = [
    "analyst",
    "data",
    "operations",
    "business intelligence",
    "bi",
    "reporting",
    "insights",
]


def fetch_greenhouse_jobs(company_slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data["jobs"]:
        jobs.append({
            "title": job["title"],
            "url": job["absolute_url"]
        })
    return jobs


def fetch_lever_jobs(company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data:
        jobs.append({
            "title": job["text"],
            "url": job["hostedUrl"]
        })
    return jobs


def fetch_ashby_jobs(company_slug):
    """
    Ashby's public API. Note: this is a different endpoint than the one
    mentioned in the original planning doc (jobs.ashbyhq.com/.../feed) --
    that one is outdated. The correct, currently-working endpoint is
    api.ashbyhq.com/posting-api/job-board/[slug].
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}?includeCompensation=false"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data["jobs"]:
        jobs.append({
            "title": job["title"],
            "url": job["jobUrl"]
        })
    return jobs


def fetch_jobs_for_company(company):
    """
    Looks at the company's 'ats' value and calls the matching fetch
    function. This is the piece that lets the main loop below stay
    simple -- it doesn't need to know or care which ATS each company
    uses, it just calls this one function and gets jobs back either way.
    """
    if company["ats"] == "greenhouse":
        return fetch_greenhouse_jobs(company["slug"])
    elif company["ats"] == "lever":
        return fetch_lever_jobs(company["slug"])
    elif company["ats"] == "ashby":
        return fetch_ashby_jobs(company["slug"])
    else:
        print(f"  Skipping {company['name']}: unknown ATS '{company['ats']}'")
        return []


def load_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE):
        return set()
    with open(SEEN_JOBS_FILE, "r") as f:
        return set(json.load(f))


def save_seen_jobs(seen_urls):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen_urls), f, indent=2)


def matches_keywords(title):
    title_lower = title.lower()
    for keyword in KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, title_lower):
            return True
    return False


def send_notification(matching_jobs):
    """
    Builds a plain-text email listing the matching jobs and sends it
    through Gmail using your app password.

    smtplib.SMTP_SSL connects to Gmail's mail server over an encrypted
    connection -- 'smtp.gmail.com' and port 465 are Gmail's standard
    settings for this, not something specific to your account.
    """
    subject = f"🎯 {len(matching_jobs)} new job match(es) found"

    body_lines = ["New job listings matching your keywords:\n"]
    for job in matching_jobs:
        body_lines.append(f"{job['title']}")
        body_lines.append(f"{job['url']}\n")
    body = "\n".join(body_lines)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, NOTIFY_EMAIL, msg.as_string())

    print(f"Email sent to {NOTIFY_EMAIL}")


def check_all_companies():
    """
    One full run: fetch every company, compare against seen jobs,
    filter for keyword matches, email if anything matches, save state.

    This is the exact same logic that used to sit directly under
    'if __name__ == "__main__":' -- it's just wrapped in a function now
    so the scheduler below can call it once immediately and then again
    every hour, instead of it only being able to run once.
    """
    seen_urls = load_seen_jobs()
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting check...")
    print(f"Loaded {len(seen_urls)} previously seen job URLs\n")

    all_current_jobs = []

    for company in COMPANIES:
        print(f"Fetching {company['name']} ({company['ats']})...")
        try:
            company_jobs = fetch_jobs_for_company(company)
            all_current_jobs += company_jobs
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Couldn't fetch {company['name']}: {e}")

    print(f"\nFound {len(all_current_jobs)} total current listings\n")

    new_jobs = []
    for job in all_current_jobs:
        if job["url"] not in seen_urls:
            new_jobs.append(job)
            seen_urls.add(job["url"])

    print(f"{len(new_jobs)} new listing(s) since last run\n")

    matching_jobs = [job for job in new_jobs if matches_keywords(job["title"])]

    if matching_jobs:
        print(f"✅ {len(matching_jobs)} match your keywords:\n")
        for job in matching_jobs:
            print(f"  - {job['title']}")
            print(f"    {job['url']}")
        send_notification(matching_jobs)
    else:
        print("None of the new listings matched your keywords. No email sent.")

    save_seen_jobs(seen_urls)
    print(f"Saved {len(seen_urls)} total job URLs to {SEEN_JOBS_FILE}")


if __name__ == "__main__":
    # GitHub sets this environment variable automatically whenever a
    # workflow runs. We use it to tell the difference between "running
    # on your laptop" (keep looping every hour forever) and "running in
    # GitHub Actions" (run once -- GitHub's own scheduler is what calls
    # this script every hour in the cloud, so we don't need our own
    # while-loop there).
    running_in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    if running_in_github_actions:
        check_all_companies()
    else:
        check_all_companies()  # run once immediately so you don't wait an hour to see it work

        schedule.every(1).hours.do(check_all_companies)
        print("\n⏰ Scheduler is running. Checking every hour. Press Ctrl+C to stop.")

        while True:
            schedule.run_pending()
            time.sleep(60)
